"""Вход публишера в Boosty со стороны бота.

* сообщение админам, когда вход слетел или вернулся (событие ``session``);
* новый вход из кук, которые админ прислал боту: файл токенов публишера и
  проверка на блоге.

Публишер шлёт событие ``session`` только при смене состояния, но после его
перезапуска первое состояние приходит снова. Флаг в Redis помнит, что админы
уже знают о поломке: одно сообщение на поломку и одно на восстановление.
"""

import json
import os
from pathlib import Path

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from sagenza_tgbot_sdk.masking import register_secrets

from services.i18n import t
from shared.boosty_cookies import auth_file_data, parse
from utils.safe_text import safe_text

DOWN_KEY = "boosty:session:down"
LOGIN_CALLBACK = "boosty:login"
API_URL = "https://api.boosty.to"
VERIFY_TIMEOUT = aiohttp.ClientTimeout(total=20)


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


def save_login(text: str, auth_file: str) -> dict:
    """Разобрать присланные куки и записать файл токенов публишера.

    Запись атомарная: публишер перечитывает файл по времени изменения и не
    должен увидеть его наполовину записанным.
    """
    data = auth_file_data(parse(text))
    register_secrets(data["access_token"], data["refresh_token"])
    target = Path(auth_file)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return data


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
