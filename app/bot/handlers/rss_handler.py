"""Кнопки уведомления о новом эпизоде из RSS (см. :mod:`services.rss`).

* «В чат» — анонс со ссылкой на эпизод в ``FORWARD_CHAT_USERNAME``.
* «На площадки» — mp3 из ``enclosure`` скачивается в ``FILES_PATH`` и
  приходит админу с обычным меню аудио: дальше FTP, сайт, Boosty и
  пересылка работают так же, как после /start.
* «Не надо» — кнопки снимаются.

После нажатия в уведомлении остаётся, кто и что выбрал.
"""

import os
from pathlib import Path

import aiofiles
import aiohttp
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, FSInputFile
from loguru import logger

from config import COVER_PS_PATH, COVER_RZ_PATH, FILES_PATH, FORWARD_CHAT_USERNAME
from filters.dispatcher_filters import IsAdmin
from handlers.menus import audio_menu_markup
from services.i18n import t
from services.redis import redis
from services.rss import ACTION_CHAT, ACTION_PREPARE, ACTION_SKIP, Episode, load_episode
from utils.podcast_methods import generate_file_name
from utils.template_store import save as save_template_info

DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)
CHUNK_SIZE = 1024 * 1024

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.callback_query.filter(IsAdmin, F.data.startswith("rss:"))


async def download_enclosure(url: str, target: Path) -> None:
    async with (
        aiohttp.ClientSession(timeout=DOWNLOAD_TIMEOUT) as session,
        session.get(url) as response,
    ):
        response.raise_for_status()
        async with aiofiles.open(target, "wb") as f:
            async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                await f.write(chunk)


async def _to_chat(bot: Bot, episode: Episode, locale: str) -> str:
    text = t("rss_chat_post", locale, title=episode.title, link=episode.link)
    try:
        await bot.send_message(chat_id=FORWARD_CHAT_USERNAME, text=text)
    except Exception as e:
        logger.error(f"rss: announce to {FORWARD_CHAT_USERNAME} failed: {e!r}")
        return t("forward_failed", locale)
    return t("rss_done_chat", locale)


async def _prepare(callback: CallbackQuery, bot: Bot, episode: Episode, locale: str) -> str:
    if not (episode.enclosure_url and episode.number and episode.type_episode):
        return t("rss_cannot_prepare", locale)
    file_name = generate_file_name(episode.number, episode.type_episode)
    target = FILES_PATH / file_name
    try:
        await download_enclosure(episode.enclosure_url, target)
    except Exception as e:
        logger.error(f"rss: download of {episode.enclosure_url} failed: {e!r}")
        target.unlink(missing_ok=True)
        return t("download_failed", locale)

    info = {
        "number": episode.number,
        "title": episode.title,
        "comment": episode.description,
        "chapters": [],
        "tags": [],
    }
    await save_template_info(file_name, info, episode.type_episode)
    await bot.send_audio(
        callback.message.chat.id,
        FSInputFile(target, file_name),
        caption=t("done_mp3", locale),
        title=episode.title,
        thumbnail=FSInputFile(COVER_RZ_PATH if episode.type_episode == "main" else COVER_PS_PATH),
        reply_markup=await audio_menu_markup(callback, episode.type_episode),
    )
    return t("rss_done_prepare", locale)


@router.callback_query()
async def on_rss_button(callback: CallbackQuery, bot: Bot, language: str, username: str):
    _prefix, action, key = callback.data.split(":", 2)
    episode = await load_episode(redis, key)
    if episode is None:
        await callback.answer(t("rss_expired", language), show_alert=True)
        return
    await callback.answer()
    logger.info(f"[{username}]: rss {action} for episode {episode.number}")

    if action == ACTION_CHAT:
        result = await _to_chat(bot, episode, language)
    elif action == ACTION_PREPARE:
        result = await _prepare(callback, bot, episode, language)
    elif action == ACTION_SKIP:
        result = t("rss_done_skip", language)
    else:
        return
    await callback.message.edit_text(
        f"{callback.message.text}\n\n{t('rss_choice', language, user=username, result=result)}",
        reply_markup=None,
    )
