"""Rich-сообщения Telegram (Bot API 10.1+): заголовки, таблицы, сворачиваемые блоки.

В клиентах это выглядит как оформленная «статья» прямо в чате. Бот шлёт
такими сообщениями то, что удобнее читать таблицей: список тем и вопросов,
состояние публикации по площадкам, ``/status``. Под сообщением работают
обычные inline-кнопки, а само оно правится на месте.

У каждого rich-сообщения есть запасной обычный текст. Он уходит вместо
таблицы, если ``RICH_MESSAGES=false`` или Telegram отказал (старый сервер
Bot API, ссылка, которую он не принимает).
"""

from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InputRichMessage, LinkPreviewOptions, Message
from loguru import logger

import config as bot_config

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
NOT_MODIFIED = "message is not modified"
# Telegram отменил правку, потому что её догнала следующая: в сообщении уже более новое.
SUPERSEDED = "canceled by new edit"
# Сообщения больше нет: его удалили из чата.
GONE = ("message to edit not found", "MESSAGE_ID_INVALID")


def enabled() -> bool:
    return bool(getattr(bot_config, "RICH_MESSAGES", True))


def is_gone(error: Exception) -> bool:
    """Telegram отказал, потому что сообщения, которое правят, уже нет."""
    return any(reason in str(error) for reason in GONE)


def cell(text: object) -> str:
    """Чужой текст для ячейки или абзаца."""
    return escape(str(text))


def table(headers: list[str], rows: list[list[str]]) -> str:
    """Таблица: заголовки экранируются, ячейки уже в HTML."""
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>" for row in rows)
    return f"<table bordered striped><tr>{head}</tr>{body}</table>"


async def send(
    bot: Bot, chat_id: int | str, html: str, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> Message:
    """Rich-сообщение; если нельзя, обычное с текстом *text*."""
    if enabled():
        try:
            return await bot.send_rich_message(
                chat_id=chat_id, rich_message=InputRichMessage(html=html), reply_markup=reply_markup
            )
        except TelegramBadRequest as error:
            logger.warning(f"rich message was not sent, falling back to text: {error!r}")
    return await bot.send_message(
        chat_id=chat_id, text=text, reply_markup=reply_markup, link_preview_options=NO_PREVIEW
    )


async def edit(
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    html: str,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Правит сообщение на месте: rich, а если нельзя, обычным текстом.

    «Ничего не изменилось» от Telegram не ошибка. Остальные отказы летят
    наружу: вызывающий решает, важна ли эта правка. Если сообщения уже нет
    (:func:`is_gone`), обычным текстом его тоже не поправить: отказ летит сразу.
    """
    if enabled():
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                rich_message=InputRichMessage(html=html),
                reply_markup=reply_markup,
            )
            return
        except TelegramBadRequest as error:
            if NOT_MODIFIED in str(error) or SUPERSEDED in str(error):
                return
            if is_gone(error):
                raise
            logger.warning(f"rich message was not edited, falling back to text: {error!r}")
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            link_preview_options=NO_PREVIEW,
        )
    except TelegramBadRequest as error:
        if NOT_MODIFIED not in str(error) and SUPERSEDED not in str(error):
            raise
