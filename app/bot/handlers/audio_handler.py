"""Кнопка «Переслать в чат» меню аудио (см. :mod:`handlers.menus`).

Подтверждение («Точно?» → «Да»/«Нет») рисует меню SDK: у кнопки
``confirm=True``, сюда нажатие доходит только после «Да».

Ход пересылки виден в отдельном статус-сообщении: отправка аудио, закреп,
проверка закрепа и итог. Ошибки Telegram переводятся в понятную админу причину.
"""

import re
from html import escape, unescape

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message
from loguru import logger
from sagenza_tgbot_sdk.menus import MenuContext

from config import FORWARD_CHAT_USERNAME, FORWARD_PIN_SILENT
from services.i18n import t
from services.metrics import TELEGRAM, bot_metrics
from utils.menu_context import username as username_of
from utils.podcast_methods import generate_podcast_text
from utils.template_store import load as load_template_info

CAPTION_LIMIT = 1024
"""Лимит подписи к аудио в Telegram — в символах видимого текста, без тегов."""

_TAG = re.compile(r"<[^>]+>")


class ForwardError(Exception):
    """Пересылка не удалась; текст — причина для админа."""


def visible_length(html_text: str) -> int:
    """Длина текста так, как её считает Telegram: без тегов и HTML-сущностей."""
    return len(unescape(_TAG.sub("", html_text)))


def explain_telegram_error(error: TelegramAPIError, action: str) -> str:
    """Переводит ошибку Telegram в причину, понятную админу."""
    text = str(error).lower()
    chat = escape(FORWARD_CHAT_USERNAME)
    if isinstance(error, TelegramForbiddenError):
        return f"{action}: бота нет в чате {chat} или ему запрещено писать туда. Добавьте бота в чат."
    if "not enough rights" in text or "chat_admin_required" in text:
        return f"{action}: у бота не хватает прав в чате {chat}. Дайте ему право закреплять сообщения."
    if "chat not found" in text:
        return f"{action}: чат {chat} не найден. Проверьте FORWARD_CHAT_USERNAME."
    if "caption is too long" in text:
        return f"{action}: подпись длиннее {CAPTION_LIMIT} символов."
    if "wrong file identifier" in text or "wrong remote file" in text:
        return f"{action}: Telegram не принял файл аудио. Загрузите эпизод заново."
    if "can't parse entities" in text:
        return f"{action}: Telegram не разобрал разметку текста поста."
    return f"{action}: {escape(str(error))}"


async def _status(status: Message, text: str) -> None:
    try:
        await status.edit_text(text, parse_mode=ParseMode.HTML)
    except TelegramAPIError as e:
        logger.warning(f"forward status not updated: {e}")


async def _send_episode(bot: Bot, audio_file_id: str, podcast_text: str) -> Message:
    """Отправляет аудио в чат; слишком длинный текст уходит отдельным ответом."""
    long_text = visible_length(podcast_text) > CAPTION_LIMIT
    caption = podcast_text.split("\n", 1)[0] if long_text else podcast_text
    try:
        sent = await bot.send_audio(
            chat_id=FORWARD_CHAT_USERNAME,
            audio=audio_file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    except TelegramAPIError as e:
        raise ForwardError(explain_telegram_error(e, "Аудио не отправлено")) from e
    if not isinstance(sent, Message) or sent.audio is None:
        raise ForwardError("Аудио не отправлено: Telegram не вернул сообщение с аудио.")

    if long_text:
        try:
            await bot.send_message(
                chat_id=FORWARD_CHAT_USERNAME,
                text=podcast_text,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=sent.message_id,
            )
        except TelegramAPIError as e:
            raise ForwardError(explain_telegram_error(e, "Аудио в чате, но текст поста не отправлен")) from e
    return sent


async def _pin_and_check(bot: Bot, message_id: int) -> None:
    """Закрепляет сообщение и убеждается, что закреплено именно оно."""
    try:
        await bot.pin_chat_message(
            chat_id=FORWARD_CHAT_USERNAME,
            message_id=message_id,
            disable_notification=FORWARD_PIN_SILENT,
        )
    except TelegramAPIError as e:
        raise ForwardError(explain_telegram_error(e, "Аудио в чате, но не закреплено")) from e

    try:
        chat = await bot.get_chat(FORWARD_CHAT_USERNAME)
    except TelegramBadRequest as e:
        logger.warning(f"pinned message check skipped: {e}")
        return
    pinned = chat.pinned_message
    if pinned is None or pinned.message_id != message_id:
        raise ForwardError("Аудио в чате, но закреп не подтвердился: закреплено другое сообщение.")


async def forward_to_chat(ctx: MenuContext):
    """Пересылает готовый эпизод в чат и закрепляет его."""
    username = username_of(ctx)
    message = ctx.message
    bot: Bot = ctx.data["bot"]
    chat = escape(FORWARD_CHAT_USERNAME)
    logger.debug(f"[{username}]: Forwarding to chat {FORWARD_CHAT_USERNAME}")

    status = None
    type_episode = None
    try:
        file_name = message.audio.file_name
        stored = await load_template_info(file_name)
        if stored is None:
            logger.warning(f"[{username}]: template info not found for {file_name}")
            await ctx.answer(t("invalid_input", ctx.locale), alert=True)
            return

        type_episode = stored.get("type_episode")
        await bot_metrics.publish_requested(TELEGRAM, type_episode, file_name=file_name)
        status = await message.answer(f"⏳ Пересылка в {chat}: отправляю аудио…", parse_mode=ParseMode.HTML)
        podcast_text = generate_podcast_text(stored["info"])
        if not podcast_text:
            raise ForwardError("Не удалось собрать текст поста из шаблона эпизода.")

        sent = await _send_episode(bot, message.audio.file_id, podcast_text)
        await _status(status, f"⏳ Пересылка в {chat}: аудио отправлено, закрепляю…")
        await _pin_and_check(bot, sent.message_id)

        logger.success(f"[{username}]: Successfully forwarded audio")
        await bot_metrics.publish_succeeded(TELEGRAM, type_episode, "published", file_name=file_name)
        await _status(status, f"✅ Эпизод опубликован в {chat} и закреплён.")
        await ctx.answer(t("forwarded", ctx.locale))

    except ForwardError as e:
        logger.error(f"[{username}]: forward_to_chat failed - {e}")
        bot_metrics.publish_failed(TELEGRAM, type_episode, "forward")
        if status is not None:
            await _status(status, f"❌ {e}")
        await ctx.answer(t("forward_failed", ctx.locale), alert=True)
    except Exception as e:
        logger.exception(f"[{username}]: Error in forward_to_chat - {e}")
        bot_metrics.publish_failed(TELEGRAM, type_episode, "forward")
        if status is not None:
            await _status(status, f"❌ Пересылка в {chat} не удалась: {escape(str(e))}")
        await ctx.answer(t("forward_failed", ctx.locale), alert=True)
    finally:
        # После «Да» на месте меню висит вопрос подтверждения — возвращаем меню.
        await ctx.show(ctx.menu_id)
