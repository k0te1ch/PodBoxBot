import asyncio
import os
import re
import shutil
import time
from collections.abc import Awaitable, Callable
from html import escape
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InputMediaAudio, Message
from aiogram.utils.chat_action import ChatActionSender
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
from forms.upload_file import DIALOG_ID, MP3, PENDING_MP3, TEMPLATE, TYPE_EPISODE, upload_file_runner
from handlers.menus import audio_menu_markup
from services.i18n import t
from services.metrics import bot_metrics
from services.none_module import _NoneModule
from services.redis import redis
from services.rss import mark_published
from utils.ftp_methods import EpisodeNumberError, get_last_post_id
from utils.mp3_methods import audio_tag, read_duration_and_artist
from utils.podcast_methods import generate_file_name
from utils.progress_callbacks import CustomFSInputFile, monitor_file_progress
from utils.status_message import StatusMessage, human_size
from utils.template_store import save as save_template_info

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)
router.callback_query.filter(IsAdmin)

runner = upload_file_runner
storage = runner.storage

# Всё, что Telegram может прислать файлом: неподходящий файл отклоняет
# сам движок по ограничениям MP3-шага, а не молчание бота.
FILE_CONTENT_TYPES = {ContentType.AUDIO, ContentType.DOCUMENT, ContentType.VOICE, ContentType.VIDEO}

# Шаги статус-сообщения (utils.status_message): тексты в локали, status_<шаг>.
DOWNLOAD = "download"
NUMBER = "number"
DESCRIPTION = "description"
TAGS = "tags"
SEND = "send"


async def _drop_keyboard(bot: Bot, anchor: MessageAnchor | None) -> None:
    """Убирает кнопки шага с сообщения, на которое диалог больше не опирается."""
    if anchor is None:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=anchor.chat_id, message_id=anchor.message_id, reply_markup=None)
    except TelegramBadRequest as e:
        logger.debug(f"step keyboard was not removed: {e!r}")


def _step_id(session) -> str:
    step = runner.engine.current_step(session) if session is not None else None
    return step.id if step is not None else "unknown"


def _step_index(step_id: str) -> int:
    ids = [step.id for step in runner.engine.steps]
    return ids.index(step_id) if step_id in ids else -1


async def _track_turn(state: FSMContext, before: str, turn: DialogTurn) -> None:
    """Шаг диалога загрузки в метриках: пройден, отклонён, отменён или истёк.

    Так видно, на каком шаге админы бросают загрузку. «Назад» не считается.
    """
    if not turn.handled:
        return
    if turn.expired:
        bot_metrics.upload_step(before, "expired")
    elif turn.cancelled:
        bot_metrics.upload_step(before, "cancelled")
    elif turn.finished:
        bot_metrics.upload_step(before, "done")
    else:
        session, _ui = await storage.load(state)
        after = _step_id(session)
        if after == before:
            bot_metrics.upload_step(before, "invalid")
        elif _step_index(after) > _step_index(before):
            bot_metrics.upload_step(before, "done")


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


class _InPlaceSender(DefaultSender):
    """Первый шаг диалога рисуется в уже показанном сообщении, а не новым.

    Так кнопка «Новый выпуск» превращает главное меню в вопрос о типе
    выпуска: чат не прыгает от лишнего сообщения.
    """

    def __init__(self, bot: Bot, chat_id: int, message_id: int) -> None:
        super().__init__(bot, chat_id)
        self._first = MessageAnchor(chat_id=chat_id, message_id=message_id)

    async def show(self, view, anchor: MessageAnchor | None) -> MessageAnchor | None:
        return await super().show(view, anchor or self._first)


async def start_upload(
    state: FSMContext,
    bot: Bot,
    message: Message,
    language: str,
    *,
    in_place: bool = True,
    pending: FileInfo | None = None,
) -> None:
    """Начинает диалог загрузки поверх любого старого.

    *in_place*: первый вопрос правит *message* (нажатие кнопки меню), иначе
    уходит новым сообщением. *pending*: mp3, с которого всё началось; после
    выбора типа выпуска он обрабатывается без повторной отправки.
    """
    bot_metrics.admin_action("upload")
    bot_metrics.upload_step("start", "done")
    chat_id = message.chat.id
    sender = _InPlaceSender(bot, chat_id, message.message_id) if in_place else DefaultSender(bot, chat_id)
    context: dict[str, Any] = {"lang": language}
    if pending is not None:
        context[PENDING_MP3] = pending.to_dict()
    await runner.start(state, sender, context=context)


@logger.catch
@router.message(F.text, Command("new"))
async def new_episode(msg: Message, state: FSMContext, bot: Bot, language: str):
    """``/new``: то же, что кнопка «Новый выпуск» главного меню."""
    await start_upload(state, bot, msg, language, in_place=False)


@logger.catch
@router.message(F.text, Command("cancel"), DialogActiveFilter(storage))
async def cancel(msg: Message, state: FSMContext, bot: Bot, language: str, username: str):
    """Отмена загрузки командой /cancel — то же, что кнопка «Отмена»."""
    logger.debug(f"[{username}]: Отмена загрузки MP3")
    session, ui = await storage.load(state)
    bot_metrics.upload_step(_step_id(session), "cancelled")
    await runner.cancel(state)
    await _drop_keyboard(bot, ui.anchor)
    await msg.reply(t("canceled", language))


@logger.catch
@router.callback_query(DialogCallbackFilter(DIALOG_ID))
async def on_dialog_button(callback: CallbackQuery, state: FSMContext, bot: Bot, language: str, username: str):
    """Кнопки диалога: выбор типа эпизода, «Назад», «Отмена»."""
    session, _ui = await storage.load(state)
    before = _step_id(session)
    turn = await runner.on_callback(callback.data, state, DefaultSender(bot, callback.message.chat.id))
    await _track_turn(state, before, turn)
    await callback.answer(text=turn.alert, show_alert=bool(turn.alert))
    if turn.cancelled and not turn.expired:
        logger.debug(f"[{username}]: Отмена загрузки MP3")
        await callback.message.edit_text(t("canceled", language))
        return
    session, _ui = await storage.load(state)
    pending = session.context.get(PENDING_MP3) if session is not None else None
    if pending and before == TYPE_EPISODE and _step_id(session) == MP3:
        # Выпуск начали с присланного mp3: тип выбран, файл уже у Telegram.
        message = callback.message
        await _take_mp3(
            message.chat.id, message.answer, [FileInfo.from_value(pending)], state, bot, language, username
        )


async def _download_mp3(mp3: FileInfo, bot: Bot, on_progress: Callable[[int], Awaitable[None]]) -> bool:
    """Скачивает присланный MP3 в PODCAST_PATH; False, если загрузка не дошла.

    *on_progress* получает число уже скачанных байт.
    """
    monitor_task = asyncio.create_task(
        monitor_file_progress(
            (Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/temp") if LOCAL else PODCAST_PATH),
            mp3.file_size,
            on_progress,
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
    await _take_mp3(msg.chat.id, msg.reply, message_files(msg), state, bot, language, username)


def _episode_title(type_episode: str, language: str) -> str:
    return "🎙 " + t("main_episode" if type_episode == "main" else "episode_aftershow", language)


async def _take_mp3(
    chat_id: int,
    reply: Callable[[str], Awaitable[Message]],
    files: list[FileInfo],
    state: FSMContext,
    bot: Bot,
    language: str,
    username: str,
) -> None:
    """Принимает mp3 на шаге MP3.

    Всё, что происходит с файлом, видно в одном сообщении: *reply* отправляет
    его, дальше оно правится (скачивание с процентами, номер выпуска) и в
    конце превращается в вопрос про описание выпуска.
    """
    sender = DefaultSender(bot, chat_id)
    session, ui = await storage.load(state)
    step = runner.engine.current_step(session) if session is not None else None
    try:
        # Сначала ограничения шага (тип, расширение, размер): качать заведомо
        # не тот файл незачем. Не тот шаг или не тот файл — ошибку покажет раннер.
        if step is None or step.id != MP3 or runner.engine.is_expired(session):
            raise ValidationError("not the mp3 step")
        validate(step, files)
    except ValidationError:
        before = _step_id(session)
        await _track_turn(state, before, await runner.on_files(files, state, sender))
        return

    await clear_old_mp3_files()

    logger.debug(f"[{username}]: Загружает MP3...")
    mp3 = files[0]
    type_episode = session.answers[TYPE_EPISODE]
    sent = await reply(t("got_mp3", language))
    status = StatusMessage(
        bot,
        chat_id,
        sent.message_id,
        _episode_title(type_episode, language),
        [DOWNLOAD, NUMBER, DESCRIPTION],
        language,
    )

    async def fail(step_key: str, outcome: str, reason: str) -> None:
        bot_metrics.upload_step(MP3, outcome)
        await status.fail(step_key, reason)
        await runner.cancel(state)
        await _drop_keyboard(bot, ui.anchor)

    received_at = time.time()
    await status.begin(DOWNLOAD)

    async def on_progress(downloaded: int) -> None:
        await status.progress(DOWNLOAD, downloaded, mp3.file_size or 0)

    async with ChatActionSender.upload_document(bot=bot, chat_id=chat_id):
        downloaded = await _download_mp3(mp3, bot, on_progress)
    if not downloaded:
        logger.warning(f"[{username}]: MP3 не загрузился")
        await fail(DOWNLOAD, "download_failed", t("download_failed", language))
        return
    bot_metrics.mp3_downloaded(time.time() - received_at)
    await status.done(DOWNLOAD, human_size(mp3.file_size or 0, language))

    try:
        async with status.ticking(NUMBER), ChatActionSender.typing(bot=bot, chat_id=chat_id):
            number = int(await get_last_post_id(type_episode, FTP_SERVER, FTP_LOGIN, FTP_PASSWORD)) + 1
    except EpisodeNumberError as e:
        # Без номера шаблон не собрать: говорим, что случилось, и закрываем
        # диалог, иначе он висит на шаге MP3 без ответа.
        logger.error(f"[{username}]: номер эпизода не получен с FTP: {e}")
        await fail(NUMBER, "number_failed", t("episode_number_failed", language, error=escape(str(e))))
        return

    # Сообщение о загрузке становится вопросом про описание: диалог дальше
    # правит его же. Со старого сообщения шага снимаются кнопки.
    await _drop_keyboard(bot, ui.anchor)
    session.context["number"] = str(number)
    session.context["mp3_size"] = human_size(mp3.file_size or 0, language)
    # Отсюда считается время до публикации на площадках.
    session.context["mp3_received_at"] = received_at
    ui.anchor = MessageAnchor(chat_id=chat_id, message_id=sent.message_id)
    await storage.save(state, session, ui)

    await _track_turn(state, MP3, await runner.on_files(files, state, sender))


def _looks_like_mp3(file: FileInfo) -> bool:
    return file.mime_type == "audio/mpeg" or file.extension == ".mp3"


@logger.catch
@router.message(F.content_type.in_(FILE_CONTENT_TYPES))
async def mp3_without_dialog(msg: Message, state: FSMContext, bot: Bot, language: str, username: str):
    """Файл вне диалога: mp3 начинает оформление выпуска, остальное получает подсказку."""
    files = message_files(msg)
    if not files or not _looks_like_mp3(files[0]):
        await msg.reply(t("file_not_mp3", language))
        return
    logger.debug(f"[{username}]: выпуск начат с присланного MP3")
    await start_upload(state, bot, msg, language, in_place=False, pending=files[0])


@logger.catch
@router.message(F.text, DialogActiveFilter(storage), flags={"long_operation": "upload_audio"})
async def set_template(msg: Message, state: FSMContext, bot: Bot, language: str, username: str):
    """Текстовый ответ диалогу; на шаге шаблона его разбирает валидатор шага."""
    session, ui = await storage.load(state)
    before = _step_id(session)
    turn = await runner.on_text(msg.text, state, DefaultSender(bot, msg.chat.id))
    await _track_turn(state, before, turn)
    if not turn.finished:
        return
    await _drop_keyboard(bot, ui.anchor)
    await publish_episode(msg, turn, language, username)


async def publish_episode(msg: Message, turn: DialogTurn, language: str, username: str) -> None:
    """Теги, переименование и отправка готового MP3 с меню публикации.

    Ход виден в одном сообщении, и оно же в конце становится готовым файлом
    с меню: бот ничего не удаляет и не присылает следом.
    """
    type_episode: str = turn.answers[TYPE_EPISODE]
    info: dict[str, Any] = turn.answers[TEMPLATE]
    bot: Bot = msg.bot
    chat_id = msg.chat.id
    logger.debug(f"[{username}]: Выбранный тип эпизода: {type_episode}")

    title = t("status_episode_title", language, number=escape(str(info["number"])), title=escape(str(info["title"])))
    sent = await msg.answer(f"<b>{title}</b>")
    status = StatusMessage(bot, chat_id, sent.message_id, title, [TAGS, SEND], language)

    logger.debug(f"[{username}]: Начинается аудиотеггинг")
    try:
        async with status.ticking(TAGS), ChatActionSender.typing(bot=bot, chat_id=chat_id):
            await asyncio.to_thread(audio_tag, info, type_episode)
            new_file_name = generate_file_name(info["number"], type_episode)
            Path(PODCAST_PATH).rename(FILES_PATH / new_file_name)
    except Exception as e:
        logger.exception(f"[{username}]: теги не проставлены: {e!r}")
        await status.fail(TAGS, t("status_tags_failed", language, error=escape(str(e))))
        return
    await status.done(TAGS)
    logger.debug(f"[{username}]: MP3-файл тегирован и переименован -> {new_file_name}")

    file = FILES_PATH / new_file_name
    size = file.stat().st_size

    async def progress_callback(bytes_uploaded: int):
        await status.progress(SEND, bytes_uploaded, size)

    duration, performer = read_duration_and_artist(file)
    await bot_metrics.episode_prepared(
        info["number"],
        type_episode,
        "upload",
        received_at=turn.context.get("mp3_received_at") or time.time(),
        size_bytes=size,
        duration_seconds=duration,
    )

    await save_template_info(new_file_name, info, type_episode)
    await mark_published(None if isinstance(redis, _NoneModule) else redis, info["number"])

    await status.begin(SEND)
    audio = {
        "caption": t("done_mp3", language),
        "duration": duration,
        "performer": performer,
        "title": info["title"],
        "thumbnail": FSInputFile(COVER_RZ_PATH if type_episode == "main" else COVER_PS_PATH),
    }
    markup = await audio_menu_markup(msg, type_episode)
    try:
        async with ChatActionSender.upload_document(bot=bot, chat_id=chat_id):
            try:
                # Статус сам становится файлом: одно сообщение вместо «удалил и прислал».
                await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=sent.message_id,
                    media=InputMediaAudio(
                        media=CustomFSInputFile(file, new_file_name, progress_callback=progress_callback), **audio
                    ),
                    reply_markup=markup,
                )
            except TelegramBadRequest as e:
                # Сервер или клиент без замены текста на файл: шлём файл отдельно.
                logger.warning(f"[{username}]: status was not turned into the audio, sending it apart: {e!r}")
                await msg.answer_audio(CustomFSInputFile(file, new_file_name), reply_markup=markup, **audio)
                await status.done(SEND)
    except TelegramAPIError as e:
        logger.exception(f"[{username}]: готовый MP3 не отправлен: {e!r}")
        await status.fail(SEND, t("status_send_failed", language, error=escape(str(e))))
        return
    logger.debug(f"[{username}]: MP3 загружен и отправлен в чат")
