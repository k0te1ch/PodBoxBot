"""Вход публишера в Boosty со стороны бота.

* сообщение админам, когда вход слетел или вернулся (событие ``session``);
* новый вход из кук, которые админ прислал боту: файл токенов публишера и
  проверка на блоге;
* периодическая проверка файла токенов из самого бота: паблишер узнаёт о
  слетевшем входе только когда пытается опубликовать, а бот будит админов
  заранее (одно сообщение на поломку и одно на восстановление).

Публишер шлёт событие ``session`` только при смене состояния, но после его
перезапуска первое состояние приходит снова. Флаг в Redis помнит, что админы
уже знают о поломке: одно сообщение на поломку и одно на восстановление.
"""

import asyncio
import json
import os
import time
from pathlib import Path

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from sagenza_tgbot_sdk.masking import register_secrets

from services.i18n import t
from shared.boosty_cookies import auth_file_data, parse, to_epoch_seconds
from utils.safe_text import safe_text

DOWN_KEY = "boosty:session:down"
LOGIN_CALLBACK = "boosty:login"
API_URL = "https://api.boosty.to"
VERIFY_TIMEOUT = aiohttp.ClientTimeout(total=20)
# access_token, который истёк или истекает в ближайшие 10 минут, проверять
# рано: обновить его должен паблишер, а параллельный refresh из бота сожжёт
# одноразовый refresh_token. Паблишер сам сообщит, если refresh не пройдёт.
REFRESH_MARGIN = 600  # сек, как REFRESH_MARGIN у паблишера


async def on_session_event(event: dict, bot: Bot, redis, admin_ids: list[int], locale: str) -> None:
    status = event.get("status")
    if status == "failure":
        if not await redis.set(DOWN_KEY, "1", nx=True):
            return
        text = t("boosty_session_down", locale, error=safe_text(event.get("error") or "-"))
        markup = login_markup(locale)
    elif status == "success":
        if not await redis.delete(DOWN_KEY):
            return
        text = t("boosty_session_restored", locale)
        markup = None
    else:
        logger.warning(f"Boosty session event with unknown status {status!r} ignored")
        return
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
        except Exception as e:
            logger.warning(f"boosty session: could not notify admin {admin_id}: {e!r}")


def login_markup(locale: str) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text=t("boosty_login_button", locale), callback_data=LOGIN_CALLBACK)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def read_login(text: str) -> dict:
    """Разобрать присланные куки в содержимое файла токенов публишера."""
    data = auth_file_data(parse(text))
    register_secrets(data["access_token"], data["refresh_token"])
    return data


def write_login(data: dict, auth_file: str) -> None:
    """Записать файл токенов публишера.

    Запись атомарная: публишер перечитывает файл по времени изменения и не
    должен увидеть его наполовину записанным.
    """
    target = Path(auth_file)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


async def verify_login(data: dict, blog: str | None) -> bool | None:
    """Пускает ли Boosty с этим входом в редактор блога.

    Только чтение черновика: refresh здесь не делается, чтобы не тратить
    одноразовый refresh_token, которым дальше пользуется публишер. ``None``,
    если блог не задан или Boosty не ответил.
    """
    if not blog:
        return None
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    if data.get("user_agent"):
        headers["User-Agent"] = data["user_agent"]
    try:
        async with (
            aiohttp.ClientSession(timeout=VERIFY_TIMEOUT) as session,
            session.get(f"{API_URL}/v1/blog/{blog}/post_draft", headers=headers) as response,
        ):
            if response.status in (401, 403):
                return False
            return True if response.status < 400 else None
    except (TimeoutError, aiohttp.ClientError) as e:
        logger.warning(f"boosty login check failed: {e!r}")
        return None


def read_auth_file(path: str) -> dict:
    """Токены из файла публишера; ошибки — с пояснением для админа."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ValueError(f"файл токенов не найден: {path}") from e
    except ValueError as e:
        raise ValueError(f"файл токенов повреждён: {path}") from e
    if not isinstance(raw, dict) or not raw.get("access_token"):
        raise ValueError(f"в файле токенов нет access_token: {path}")
    return raw


def _file_stamp(path: str) -> tuple[int, int] | None:
    """Время изменения и размер: по ним видно, что файл переписали."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


async def watch_tick(bot: Bot, redis, admin_ids: list[int], locale: str, auth_file: str, blog: str | None) -> None:
    """Одна проверка входа; состояние админам уходит через ``on_session_event``
    (тот же флаг DOWN_KEY, что и у событий паблишера: без дублей)."""
    try:
        data = read_auth_file(auth_file)
    except ValueError as e:
        await on_session_event({"status": "failure", "error": safe_text(e)}, bot, redis, admin_ids, locale)
        return
    expires_at = to_epoch_seconds(data.get("expires_at"))
    if expires_at is not None and time.time() + REFRESH_MARGIN >= expires_at:
        # access_token умер или умирает: refresh — работа паблишера, бот не
        # тратит одноразовый refresh_token. Плохой refresh паблишер и так
        # сообщит событием session.
        logger.debug("boosty watch: access token expired or expiring, refresh is the publisher's job")
        return
    stamp = _file_stamp(auth_file)
    verified = await verify_login(data, blog)
    if verified is False and stamp is not None and stamp != _file_stamp(auth_file):
        # Пока проверяли, файл переписали (паблишер обновил токен или админ
        # прислал новые куки): проверяем уже свежую пару, прежде чем будить.
        data = read_auth_file(auth_file)
        verified = await verify_login(data, blog)
    if verified is True:
        await on_session_event({"status": "success"}, bot, redis, admin_ids, locale)
    elif verified is False:
        await on_session_event(
            {"status": "failure", "error": "токен не пускает в редактор блога"}, bot, redis, admin_ids, locale
        )
    # None (Boosty не ответил или блог не задан) — не повод для тревоги.


async def watch_boosty_login(
    bot: Bot, redis, admin_ids: list[int], locale: str, auth_file: str, blog: str | None, interval: int
) -> None:
    """Цикл периодической проверки входа; падения тика логируются и не рвут цикл."""
    logger.info(f"boosty watch: checking {auth_file} every {interval}s")
    while True:
        try:
            await watch_tick(bot, redis, admin_ids, locale, auth_file, blog)
        except Exception as e:
            logger.warning(f"boosty watch: tick failed: {e!r}")
        await asyncio.sleep(interval)
