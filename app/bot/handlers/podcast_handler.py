import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from dialog_engine import FileInfo, ValidationError, validate
from dialog_engine.integrations.aiogram import (
    DefaultSender,
    DialogActiveFilter,
    DialogCallbackFilter,
    DialogTurn,
    MessageAnchor,
    message_files,
)
from loguru import logger

from config import (
    API_TOKEN,
    COVER_PS_PATH,
    COVER_RZ_PATH,
    FILES_PATH,
    FTP_LOGIN,
    FTP_PASSWORD,
    FTP_SERVER,
    LOCAL,
    PODCAST_PATH,
)
from filters.dispatcher_filters import IsAdmin, IsPrivate
from forms.upload_file import DIALOG_ID, MP3, TEMPLATE, TYPE_EPISODE, upload_file_runner
from handlers.menus import audio_menu_markup
from services.i18n import t
from services.none_module import _NoneModule
from services.redis import redis
from services.rss import mark_published
from utils.ftp_methods import get_last_post_id
from utils.mp3_methods import audio_tag, read_duration_and_artist
from utils.podcast_methods import generate_file_name
from utils.progress_callbacks import (
    CustomFSInputFile,
    monitor_file_progress,
    telegram_progress_callback,
)
from utils.template_store import save as save_template_info

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)
router.callback_query.filter(IsAdmin)

runner = upload_file_runner
storage = runner.storage

# Всё, что Telegram может прислать файлом: неподходящий файл отклоняет
# сам движок по ограничениям MP3-шага, а не молчание бота.
FILE_CONTENT_TYPES = {ContentType.AUDIO, ContentType.DOCUMENT, ContentType.VOICE, ContentType.VIDEO}


async def _drop_keyboard(bot: Bot, anchor: MessageAnchor | None) -> None:
    """Убирает кнопки шага с сообщения, на которое диалог больше не опирается."""
    if anchor is None:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=anchor.chat_id, message_id=anchor.message_id, reply_markup=None)
    except TelegramBadRequest as e:
        logger.debug(f"step keyboard was not removed: {e!r}")


async def clear_old_mp3_files():
    """Удаляет старые MP3-файлы и их sidecar-метаданные."""
    for item in FILES_PATH.iterdir():
        if item.is_file() and item.suffix in {".mp3", ".json"}:
            item.unlink()

    if LOCAL:
        music_path = Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/music")
        temp_path = Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/temp")

        for folder in [music_path, temp_path]:
            if folder.exists():
                for item in folder.iterdir():
                    if item.is_file():
                        item.unlink()

    logger.debug("Старые MP3-файлы удалены")


@logger.catch
@router.message(F.text, CommandStart())
async def start(msg: Message, state: FSMContext, bot: Bot, language: str):
    """Обработчик команды /start: новый диалог загрузки поверх любого старого."""
    await runner.start(
        state,
        DefaultSender(bot, msg.chat.id),
        context={"lang": language, "first_name": msg.from_user.first_name},
    )


@logger.catch
@router.message(F.text, Command("cancel"), DialogActiveFilter(storage))
async def cancel(msg: Message, state: FSMContext, bot: Bot, language: str, username: str):
    """Отмена загрузки командой /cancel — то же, что кнопка «Отмена»."""
    logger.debug(f"[{username}]: Отмена загрузки MP3")
    _session, ui = await storage.load(state)
    await runner.cancel(state)
    await _drop_keyboard(bot, ui.anchor)
    await msg.reply(t("canceled", language))


@logger.catch
@router.callback_query(DialogCallbackFilter(DIALOG_ID))
async def on_dialog_button(callback: CallbackQuery, state: FSMContext, bot: Bot, language: str, username: str):
    """Кнопки диалога: выбор типа эпизода, «Назад», «Отмена»."""
    turn = await runner.on_callback(callback.data, state, DefaultSender(bot, callback.message.chat.id))
    await callback.answer(text=turn.alert, show_alert=bool(turn.alert))
    if turn.cancelled and not turn.expired:
        logger.debug(f"[{username}]: Отмена загрузки MP3")
        await callback.message.edit_text(t("canceled", language))


async def _download_mp3(mp3: FileInfo, bot: Bot, download_msg: Message) -> bool:
    """Скачивает присланный MP3 в PODCAST_PATH; False, если загрузка не дошла."""

    async def progress_callback(bytes_uploaded: int):
        await telegram_progress_callback(bytes_uploaded, download_msg, mp3.file_size)

    monitor_task = asyncio.create_task(
        monitor_file_progress(
            (Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/temp") if LOCAL else PODCAST_PATH),
            mp3.file_size,
            progress_callback,
            (Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/music") if LOCAL else PODCAST_PATH),
        )
    )
    file = await bot.get_file(mp3.file_id, 600)
    file_path = Path(file.file_path)

    await asyncio.sleep(0.1)

    if LOCAL:
        match = re.findall(r"[\\/]{1}music[\\/](.*?)$", str(file_path))
        if match:
            source_path = Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/music") / match[0]
            destination_path = Path(PODCAST_PATH)
            shutil.move(str(source_path), str(destination_path))
    else:
        await bot.download(mp3.file_id, PODCAST_PATH, timeout=60)

    while not monitor_task.done():
        await asyncio.sleep(0.1)

    # monitor_file_progress возвращает bool (или None, если @logger.catch его
    # задушил). False/None — загрузка не дошла.
    return bool(monitor_task.result())


@logger.catch
@router.message(DialogActiveFilter(storage), F.content_type.in_(FILE_CONTENT_TYPES))
async def get_MP3(msg: Message, state: FSMContext, bot: Bot, language: str, username: str):
    """Файл на шаге MP3: проверка ограничений шага, скачивание, номер эпизода."""
    sender = DefaultSender(bot, msg.chat.id)
    files = message_files(msg)
    session, ui = await storage.load(state)
    step = runner.engine.current_step(session) if session is not None else None
    try:
        # Сначала ограничения шага (тип, расширение, размер): качать заведомо
        # не тот файл незачем. Не тот шаг или не тот файл — ошибку покажет раннер.
        if step is None or step.id != MP3 or runner.engine.is_expired(session):
            raise ValidationError("not the mp3 step")
        validate(step, files)
    except ValidationError:
        await runner.on_files(files, state, sender)
        return

    await clear_old_mp3_files()

    logger.debug(f"[{username}]: Загружает MP3...")
    download_msg = await msg.reply(t("got_mp3", language))

    if not await _download_mp3(files[0], bot, download_msg):
        logger.warning(f"[{username}]: MP3 не загрузился")
        await download_msg.edit_text(t("download_failed", language))
        await runner.cancel(state)
        await _drop_keyboard(bot, ui.anchor)
        return

    type_episode = session.answers[TYPE_EPISODE]
    number = int(await get_last_post_id(type_episode, FTP_SERVER, FTP_LOGIN, FTP_PASSWORD)) + 1

    # Шаблон уходит новым сообщением под скачанным файлом: старое сообщение
    # шага осталось выше по чату, с него снимаются кнопки.
    await _drop_keyboard(bot, ui.anchor)
    session.context["number"] = str(number)
    ui.anchor = None
    await storage.save(state, session, ui)

    await download_msg.edit_text(t("downloaded", language))
    await runner.on_files(files, state, sender)


@logger.catch
@router.message(F.text, DialogActiveFilter(storage), flags={"long_operation": "upload_audio"})
async def set_template(msg: Message, state: FSMContext, bot: Bot, language: str, username: str):
    """Текстовый ответ диалогу; на шаге шаблона его разбирает валидатор шага."""
    _session, ui = await storage.load(state)
    turn = await runner.on_text(msg.text, state, DefaultSender(bot, msg.chat.id))
    if not turn.finished:
        return
    await _drop_keyboard(bot, ui.anchor)
    await publish_episode(msg, turn, language, username)


async def publish_episode(msg: Message, turn: DialogTurn, language: str, username: str) -> None:
    """Теги, переименование и отправка готового MP3 с меню публикации."""
    type_episode: str = turn.answers[TYPE_EPISODE]
    info: dict[str, Any] = turn.answers[TEMPLATE]
    logger.debug(f"[{username}]: Выбранный тип эпизода: {type_episode}")

    tmp1 = await msg.answer(t("set_tags", language))

    logger.debug(f"[{username}]: Начинается аудиотеггинг")
    await asyncio.to_thread(audio_tag, info, type_episode)

    new_file_name = generate_file_name(info["number"], type_episode)
    Path(PODCAST_PATH).rename(FILES_PATH / new_file_name)

    logger.debug(f"[{username}]: MP3-файл тегирован и переименован -> {new_file_name}")

    file = FILES_PATH / new_file_name
    try:
        await tmp1.delete()
    except Exception as e:
        logger.error(f"Ошибка при удалении tmp1: {e}")
    tmp = await msg.answer(t("done_tag", language))

    async def progress_callback(bytes_uploaded: int):
        await telegram_progress_callback(bytes_uploaded, tmp, file.stat().st_size)

    duration, performer = read_duration_and_artist(file)

    await save_template_info(new_file_name, info, type_episode)
    await mark_published(None if isinstance(redis, _NoneModule) else redis, info["number"])

    await msg.reply_audio(
        CustomFSInputFile(file, new_file_name, progress_callback=progress_callback),
        caption=t("done_mp3", language),
        duration=duration,
        performer=performer,
        title=info["title"],
        thumbnail=FSInputFile(COVER_RZ_PATH if type_episode == "main" else COVER_PS_PATH),
        reply_markup=await audio_menu_markup(msg, type_episode),
    )

    await tmp.delete()
    logger.debug(f"[{username}]: MP3 загружен и отправлен в чат")
