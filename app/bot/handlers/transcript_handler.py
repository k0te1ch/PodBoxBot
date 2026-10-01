"""Эксперимент: что бот делает с готовой расшифровкой выпуска.

Расшифровывает отдельный сервис ``transcriber`` (:mod:`shared.transcribe`),
бот только ждёт итог и пишет админам в личку:

* ключевые слова выпуска, из которых удобно собрать хештеги, и саму
  расшифровку файлом;
* если включены темы от слушателей: какие пункты списка, похоже, обсудили.
  Бот показывает список, где эти пункты уже отмечены к удалению, и спрашивает,
  удалить ли их. Удаляет те же кнопки, что и под обычным списком, так что
  отметки можно поправить, а удалённое вернуть.

Всё это подсказки по словам из расшифровки, без моделей и внешних сервисов
(:mod:`services.transcripts`): решает ведущий. Работает, только когда включён
``TRANSCRIBE_ENABLED``.
"""

import asyncio
import os
from typing import Any

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters.callback_data import CallbackData
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

import config as bot_config
from handlers.topics_list_view import MARKED_PREFIX, REMOVE, ListCallback, numbers_text, send_list
from services.i18n import DEFAULT_LOCALE, t
from services.metrics import bot_metrics
from services.topics.runtime import is_admin, topic_list, topics_enabled
from services.transcripts.keywords import as_hashtags, suggest_keywords
from services.transcripts.lemmas import Lemma, lemmatize
from services.transcripts.matching import match_items
from services.transcripts.requests import transcribe_enabled
from shared.transcribe import DONE, Result, result_key

POLL_SECONDS = 30
RETRY_SECONDS = 15
KEEP = "k"


class TranscriptCallback(CallbackData, prefix="tr"):
    a: str


def _episode(result: Result) -> str:
    return result.job.number or result.job.file


def summary_text(result: Result, keywords: list[str], locale: str = DEFAULT_LOCALE) -> str:
    """Что получилось: сколько аудио, за сколько, какие слова годятся в хештеги."""
    lines = [
        t(
            "transcript_done",
            locale,
            episode=_episode(result),
            audio=round(result.audio_seconds / 60),
            minutes=max(round(result.seconds / 60), 1),
        )
    ]
    if keywords:
        lines.append(t("transcript_keywords", locale, hashtags=as_hashtags(keywords)))
    else:
        lines.append(t("transcript_no_keywords", locale))
    return "\n".join(lines)


async def discussed_item_ids(transcript: list[Lemma]) -> list[int]:
    """Пункты списка тем и вопросов, которые похожи на обсуждённые в выпуске."""
    if not topics_enabled():
        return []
    items = await topic_list().repository.items()
    matches = await asyncio.to_thread(match_items, transcript, [(item.id, item.text) for item in items])
    return [match.item_id for match in matches]


async def _send_summary(bot: Bot, chat_id: int, result: Result, text: str) -> None:
    name = f"{_episode(result)}_transcript.txt".replace("/", "_")
    document = BufferedInputFile(result.text.encode("utf-8"), filename=name)
    await bot.send_document(chat_id=chat_id, document=document, caption=text)


async def _suggest_removal(bot: Bot, chat_id: int, item_ids: list[int], locale: str) -> None:
    """Список с отмеченными пунктами и вопрос, удалить ли их."""
    view = await send_list(bot, chat_id, locale, private=True, marked_ids=item_ids)
    if not view.marked:
        # Пока расшифровка шла, пункты уже убрали из списка.
        return
    remove = InlineKeyboardButton(
        text=MARKED_PREFIX + t("transcript_remove", locale),
        callback_data=ListCallback(a=REMOVE, v=view.token).pack(),
    )
    keep = InlineKeyboardButton(text=t("transcript_keep", locale), callback_data=TranscriptCallback(a=KEEP).pack())
    await bot.send_message(
        chat_id=chat_id,
        text=t("transcript_discussed", locale, numbers=numbers_text(view.marked)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[remove, keep]]),
    )


async def report(bot: Bot, result: Result) -> None:
    """Рассказать админам об итоге расшифровки."""
    locale = DEFAULT_LOCALE
    if result.error is not None:
        bot_metrics.event("transcript", result="failed")
        text = t("transcript_failed", locale, episode=_episode(result), reason=result.error)
        await _to_admins(bot, lambda chat_id: bot.send_message(chat_id=chat_id, text=text))
        return
    bot_metrics.event("transcript", result="done")
    transcript = await asyncio.to_thread(lemmatize, result.text)
    summary = summary_text(result, suggest_keywords(transcript), locale)
    item_ids = await discussed_item_ids(transcript)
    bot_metrics.event("transcript_match", found="yes" if item_ids else "no")

    async def tell(chat_id: int) -> None:
        await _send_summary(bot, chat_id, result, summary)
        if item_ids:
            await _suggest_removal(bot, chat_id, item_ids, locale)

    await _to_admins(bot, tell)


async def _to_admins(bot: Bot, send: Any) -> None:
    if not bot_config.ADMINS_ID:
        logger.warning("transcript: ADMINS_ID is empty, nobody to tell about the result")
    for chat_id in bot_config.ADMINS_ID:
        try:
            await send(chat_id)
        except TelegramAPIError as error:
            logger.warning(f"transcript: admin {chat_id} is not reachable: {error!r}")


async def handle_done(bot: Bot, redis: Any, job_id: str) -> None:
    raw = await redis.get(result_key(job_id))
    if not raw:
        logger.warning(f"transcribe {job_id}: the result is gone")
        return
    await report(bot, Result.from_json(raw))


async def watch_transcripts(bot: Bot, redis: Any, *, poll_seconds: int = POLL_SECONDS) -> None:
    """Фоновая задача бота: ждать готовые расшифровки и рассказывать о них."""
    logger.info("transcripts: waiting for results")
    while True:
        try:
            popped = await redis.blpop(DONE, timeout=poll_seconds)
            if popped is not None:
                await handle_done(bot, redis, popped[1])
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception(f"transcripts: could not handle a result: {error!r}")
            await asyncio.sleep(RETRY_SECONDS)


router = Router(name=os.path.splitext(os.path.basename(__file__))[0])


def _admin_in_private(callback: CallbackQuery) -> bool:
    message = callback.message
    return isinstance(message, Message) and message.chat.type == ChatType.PRIVATE and is_admin(callback)


@router.callback_query(transcribe_enabled, TranscriptCallback.filter(), _admin_in_private)
async def keep_items(callback: CallbackQuery, bot: Bot):
    """«Оставить»: список показывается заново, уже без отметок."""
    message = callback.message
    locale = DEFAULT_LOCALE
    await callback.answer()
    await message.edit_text(t("transcript_kept", locale))
    await send_list(bot, message.chat.id, locale, private=True)
