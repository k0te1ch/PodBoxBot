"""Статус-сообщение публикации: начало, ход и итог каждого шага.

Publisher'ы присылают в result-топик события трёх видов:

* ``progress`` со ``status="pending"`` и ``metadata.stage`` — начался шаг;
* ``progress`` со ``status="uploading"`` и долей ``progress`` — ход загрузки (FTP);
* ``result`` со статусом ``success`` / ``failure`` / ``retrying``.

Всё это правит одно и то же сообщение, которое бот отправил при нажатии кнопки.
Текст — HTML с экранированием: в Markdown имена файлов вида ``001_rz_...mp3`` и
тексты ошибок ломали разметку, и Telegram отказывался править сообщение.
"""

import asyncio
from html import escape

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from loguru import logger

STAGE_TITLES = {
    "upload": "загрузка файла на FTP",
    "publish": "публикация поста",
    "verify": "проверка, что пост доступен",
    "container": "поиск блога",
    "upload_audio": "загрузка аудио",
    "upload_image": "загрузка обложки",
}

EPISODE_TITLES = {"main": "основной эпизод", "aftershow": "послешоу", "postshow": "послешоу"}

# ``metadata.platform`` success-события (имя publisher'а) -> где опубликовано.
PLATFORM_PLACES = {
    "wp": "на сайте",
    "boosty": "на Boosty",
    "vk": "в VK Donut",
    "patreon": "на Patreon",
    "sponsr": "на Sponsr",
}

# Сколько раз переждать flood-лимит Telegram для итогового сообщения.
FINAL_EDIT_ATTEMPTS = 3

# Сколько последних завершённых сообщений помнить, чтобы опоздавший прогресс не
# затёр итог.
FINISHED_LIMIT = 256


def _stage(event: dict) -> str | None:
    """Шаг публикации из ``metadata`` (publisher'ы присылают его не всегда)."""
    metadata = event.get("metadata") or {}
    return metadata.get("stage")


def stage_title(stage: str) -> str:
    """Человекочитаемое название шага, для незнакомого — сам идентификатор."""
    return STAGE_TITLES.get(stage, stage)


def _subject(event: dict) -> str:
    """О чём сообщение: эпизод по номеру или файл по имени."""
    number = event.get("number")
    if number:
        return f"Эпизод <b>{escape(str(number))}</b>"
    subject = f"Файл <b>{escape(event.get('file_name') or '')}</b>"
    if kind := EPISODE_TITLES.get(event.get("type_episode") or ""):
        subject += f" ({kind})"
    return subject


def _success_text(event: dict) -> str:
    """Итог успешной публикации словами того, что площадка сделала на самом деле.

    Publisher кладёт в ``metadata`` площадку (``platform``) и действие
    (``action``: ``published``, ``draft``, ``scheduled`` с ``publish_at``).
    Без действия (старый publisher) текст ничего не обещает.
    """
    number = event.get("number")
    if not number:
        return f"✅ {_subject(event)} успешно загружен!"

    metadata = event.get("metadata") or {}
    episode = f"<b>{escape(str(number))}</b>"
    platform = metadata.get("platform")
    where = f" {PLATFORM_PLACES.get(platform, f'на {escape(platform)}')}" if platform else ""

    action = metadata.get("action")
    if action == "published":
        return f"✅ Эпизод {episode} опубликован{where}"
    if action == "draft":
        return f"✅ Эпизод {episode}: пост сохранён в черновики{where}, подписчики его пока не видят"
    if action == "scheduled":
        when = f" на {escape(publish_at)}" if (publish_at := metadata.get("publish_at")) else ""
        return f"✅ Эпизод {episode}: отложенная публикация{where} запланирована{when}"
    return f"✅ Эпизод {episode}: публикация{where} завершена"


def _percent(progress) -> float:
    """Доля 0..1 из publisher'а или уже готовые проценты."""
    if isinstance(progress, float) and progress <= 1:
        return progress * 100
    return float(progress or 0)


class TelegramUpdater:
    """Правит статус-сообщение публикации по событиям publisher'ов."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._finished: dict[tuple[str, str], None] = {}

    async def update_upload_progress(self, event: dict, finished: bool = False):
        """Начало шага или ход загрузки."""
        chat_id, message_id = event.get("chat_id"), event.get("message_id")
        if not chat_id or not message_id:
            logger.warning(f"Missing chat_id or message_id in event: {event}")
            return
        if self._is_finished(chat_id, message_id):
            logger.debug(f"Progress after the final status ignored: {event}")
            return

        if finished:
            text = f"✅ {_subject(event)} успешно загружен!"
        elif event.get("status") == "pending" and (stage := _stage(event)):
            text = f"⏳ {_subject(event)}: {escape(stage_title(stage))}…"
        else:
            text = f"📤 {_subject(event)}: загрузка\nПрогресс: {_percent(event.get('progress')):.1f}%"
            if speed := event.get("transfer_speed"):
                text += f" ({speed / 1024 / 1024:.1f} МБ/с)"

        await self._edit(chat_id, message_id, text)

    async def update_upload_result(self, event: dict, success: bool, error: str | None = None):
        """Итог публикации (FTP/WordPress/Boosty)."""
        chat_id, message_id = event.get("chat_id"), event.get("message_id")
        if not chat_id or not message_id:
            logger.warning(f"Missing chat_id or message_id in event: {event}")
            return

        number = event.get("number")
        if success:
            text = _success_text(event)
            url = (event.get("metadata") or {}).get("url")
            if url:
                text += f"\n{escape(url)}"
        else:
            if number:
                text = f"❌ Ошибка публикации эпизода <b>{escape(str(number))}</b>"
            else:
                text = f"❌ Ошибка загрузки: {_subject(event)}"
            if stage := _stage(event):
                text += f" на шаге <code>{escape(stage)}</code> ({escape(stage_title(stage))})"
            if error:
                text += f"\n<code>{escape(error)}</code>"

        self._mark_finished(chat_id, message_id)
        await self._edit(chat_id, message_id, text, final=True)

    async def update_upload_retry(self, event: dict):
        """Попытка шага не удалась, publisher повторяет её."""
        chat_id, message_id = event.get("chat_id"), event.get("message_id")
        if not chat_id or not message_id:
            logger.warning(f"Missing chat_id or message_id in event: {event}")
            return

        metadata = event.get("metadata") or {}
        attempt = metadata.get("attempt", "?")
        attempts = metadata.get("attempts", "?")
        stage = metadata.get("stage", "?")
        text = (
            f"🔁 {_subject(event)}: попытка {escape(attempt)}/{escape(attempts)} "
            f"не удалась на шаге <code>{escape(stage)}</code>, повторяю"
        )
        if error := event.get("error"):
            text += f"\n<code>{escape(error)}</code>"
        await self._edit(chat_id, message_id, text)

    def _is_finished(self, chat_id, message_id) -> bool:
        return (str(chat_id), str(message_id)) in self._finished

    def _mark_finished(self, chat_id, message_id) -> None:
        self._finished[(str(chat_id), str(message_id))] = None
        while len(self._finished) > FINISHED_LIMIT:
            del self._finished[next(iter(self._finished))]

    async def _edit(self, chat_id, message_id, text: str, final: bool = False) -> None:
        """Правит сообщение; итог переживает flood-лимит, промежуточные — нет."""
        attempts = FINAL_EDIT_ATTEMPTS if final else 1
        for attempt in range(1, attempts + 1):
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id, text=text, parse_mode=ParseMode.HTML
                )
                return
            except TelegramRetryAfter as e:
                if attempt == attempts:
                    logger.error(f"Статус-сообщение не обновлено из-за flood-лимита: {e}")
                    return
                await asyncio.sleep(e.retry_after)
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    logger.error(f"Ошибка обновления Telegram-сообщения: {e}")
                return
            except Exception as e:
                logger.error(f"Ошибка обновления Telegram-сообщения: {e}")
                return
