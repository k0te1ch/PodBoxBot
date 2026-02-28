import asyncio
import os
import re
import shutil
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message, ReplyKeyboardRemove
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
from filters.dispatcher_filters import ContextButton, IsAdmin, IsPrivate
from forms.upload_file import UploadFile
from services import context, keyboards
from utils.FTP_methods import get_last_post_ID
from utils.MP3_methods import audio_tag
from utils.podcast_methods import generate_file_name
from utils.progress_callbacks import (
    CustomFSInputFile,
    monitor_file_progress,
    telegram_progress_callback,
)
from utils.validators import validate_template

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)


async def clear_old_mp3_files():
    """Удаляет старые MP3-файлы."""
    for item in FILES_PATH.iterdir():
        if item.suffix == ".mp3" and item.is_file():
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
async def start(msg: Message, state: FSMContext, language: str):
    """Обработчик команды /start"""
    await msg.reply(
        context[language].ask_typeEpisode,
        reply_markup=keyboards["podcast_handler"][language].type_episode,
    )
    await state.set_state(UploadFile.type_episode)


@logger.catch
@router.message(F.text, ContextButton("cancel"), StateFilter(UploadFile))
async def cancel(msg: Message, state: FSMContext, language: str, username: str):
    """Отмена загрузки MP3."""
    logger.debug(f"[{username}]: Отмена загрузки MP3")
    await msg.reply(
        context[language].canceled,
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.clear()


@logger.catch
@router.message(
    F.text,
    ContextButton(["main_episode", "episode_aftershow"]),
    UploadFile.type_episode,
)
async def get_type(msg: Message, state: FSMContext, language: str, username: str):
    """Выбор типа эпизода."""
    type_episode = "main" if msg.text == context[language].main_episode else "aftershow"
    await state.update_data(type_episode=type_episode)
    logger.debug(f"[{username}]: Выбран тип эпизода: {type_episode}")

    type_episode_text = (
        "основной эпизод" if type_episode == "main" else "эпизод послешоу"
    )
    await msg.reply(
        context[language].ask_mp3,
        reply_markup=keyboards["podcast_handler"][language].cancel,
    )
    await state.set_state(UploadFile.mp3)


@logger.catch
@router.message(UploadFile.mp3, F.audio)
async def get_MP3(
    msg: Message, state: FSMContext, bot: Bot, language: str, username: str
):
    """Обработка загрузки MP3."""
    await clear_old_mp3_files()

    logger.debug(f"[{username}]: Загружает MP3...")
    download_msg = await msg.reply(context[language].got_mp3)

    async def progress_callback(bytes_uploaded: int):
        await telegram_progress_callback(
            bytes_uploaded, download_msg, msg.audio.file_size
        )

    monitor_task = asyncio.create_task(
        monitor_file_progress(
            (
                Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/temp")
                if LOCAL
                else PODCAST_PATH
            ),
            msg.audio.file_size,
            progress_callback,
            (
                Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/music")
                if LOCAL
                else PODCAST_PATH
            ),
        )
    )
    file = await bot.get_file(msg.audio.file_id, 600)
    file_path = Path(file.file_path)

    match = re.findall(r"[\\/]{1}music[\\/](.*?)$", str(file_path))

    await asyncio.sleep(0.1)

    if LOCAL:
        match = re.findall(r"[\\/]{1}music[\\/](.*?)$", str(file_path))
        if match:
            source_path = (
                Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/music") / match[0]
            )
            destination_path = Path(PODCAST_PATH)
            shutil.move(str(source_path), str(destination_path))
    else:
        await bot.download(msg.audio.file_id, PODCAST_PATH, timeout=60)

    while not monitor_task.done():
        await asyncio.sleep(0.1)

    episode_data = await state.get_data()
    type_episode = episode_data["type_episode"]

    numberLastEpisode = str(
        int(await get_last_post_ID(type_episode, FTP_SERVER, FTP_LOGIN, FTP_PASSWORD))
        + 1
    )

    await download_msg.edit_text(context[language].downloaded)
    await msg.answer(
        context.ask_template[type_episode].replace("600", numberLastEpisode),
        reply_markup=keyboards["podcast_handler"][language].cancel,
    )
    await state.set_state(UploadFile.template)


@logger.catch
@router.message(F.text, UploadFile.template, flags={"long_operation": "upload_audio"})
async def set_template(msg: Message, state: FSMContext, language: str, username: str):
    """Обработка шаблона для MP3-тегов."""
    type_episode = (await state.get_data())["type_episode"]
    logger.debug(f"[{username}]: Выбранный тип эпизода: {type_episode}")

    info = validate_template(msg.text)
    if info is None:
        logger.debug(f"[{username}]: Ошибка в шаблоне")
        return await msg.reply(context[language].invalid_input)

    tmp1 = await msg.answer(
        context[language].set_tags, reply_markup=ReplyKeyboardRemove()
    )

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
    tmp = await msg.answer(context[language].done_tag)

    async def progress_callback(bytes_uploaded: int):
        await telegram_progress_callback(bytes_uploaded, tmp, file.stat().st_size)

    import eyed3

    af = eyed3.load(file)

    await msg.reply_audio(
        CustomFSInputFile(file, new_file_name, progress_callback=progress_callback),
        caption=context[language].done_mp3,
        duration=int(af.info.time_secs),
        performer=af.tag.artist,
        title=info["title"],
        thumbnail=FSInputFile(
            COVER_RZ_PATH if type_episode == "main" else COVER_PS_PATH
        ),
        reply_markup=(
            keyboards["podcast_handler"][language].audio_menu_main
            if type_episode == "main"
            else keyboards["podcast_handler"][language].audio_menu_post
        ),
    )

    await tmp.delete()
    logger.debug(f"[{username}]: MP3 загружен и отправлен в чат")
    await state.clear()
