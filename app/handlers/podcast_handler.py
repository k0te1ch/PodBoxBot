from pathlib import Path
import shutil
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message, ReplyKeyboardRemove
from loguru import logger

from config import (
    FILES_PATH,
    FTP_LOGIN,
    FTP_PASSWORD,
    FTP_SERVER,
    LOCAL,
    PODCAST_PATH,
    TIMEZONE,
)
from forms.upload_file import UploadFile
from utils.FTP_methods import get_last_post_ID
from services.context import context
from filters.dispatcher_filters import ContextButton, IsAdmin, IsPrivate
from services.keyboards import keyboards
from utils.MP3_methods import audio_tag
from utils.validators import validate_template


router = Router(name="podcast_handler")
router.message.filter(IsPrivate, IsAdmin)


@logger.catch
@router.message(F.text, CommandStart())
async def start(msg: Message, state: FSMContext, language: str, username: str) -> None:
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Called <b>/start</b> command")
    await msg.reply(
        context[language].ask_typeEpisode,
        reply_markup=keyboards["podcast_handler"][language].typeEpisode,
    )
    await state.set_state(UploadFile.typeEpisode)


#TODO: rework this
@logger.catch
@router.message(F.text, ContextButton("cancel"), StateFilter(UploadFile))
async def cancel(msg: Message, state: FSMContext, language: str, username: str) -> None:
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Cancel MP3 tagging")
    await msg.reply(
        context[language].canceled,
        reply_markup=ReplyKeyboardRemove(remove_keyboard=True),
    )
    await state.clear()


@logger.catch
@router.message(F.text, ContextButton(["main_episode", "episode_aftershow"]), UploadFile.typeEpisode)
async def get_type(msg: Message, state: FSMContext, language: str, username: str) -> None:
    await state.update_data(typeEpisode="main" if msg.text == context[language].main_episode else "aftershow")
    await state.set_state(UploadFile.mp3)
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Get type of episode")
    typeEpisode = msg.text.lower()  #! context for formatting, don't touch!
    #TODO: refactoring this shit (in the future...)
    await msg.reply(
        context[language].ask_mp3,
        reply_markup=keyboards["podcast_handler"][language].cancel,
    )


@logger.catch
@router.message(UploadFile.mp3, F.audio)
async def get_MP3(msg: Message, state: FSMContext, bot: Bot, language: str, username: str) -> None:
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Got MP3, downloading...")
    download_msg = await msg.reply(context[language].got_mp3)
    for item in FILES_PATH.iterdir():
        if item.suffix == ".mp3" and item.is_file():
            item.unlink()
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Deleted previous MP3 files")

    if LOCAL:
        #TODO: MORE LOGGING FOR THE GOD OF LOGGING
        from re import findall

        from config import API_TOKEN

        file = await bot.get_file(msg.audio.file_id)
        file_path = Path(file.file_path)
        match = findall(r"[\\/]{1}music[\\/](.*?)$", str(file_path))

        if match: # TODO: Добавить обработку ошибок
            source_path = Path(f"/var/lib/telegram-bot-api/{API_TOKEN}/music") / match[0]
            destination_path = Path(PODCAST_PATH)
            shutil.move(str(source_path), str(destination_path))
    else:
        await bot.download(msg.audio.file_id, PODCAST_PATH, timeout=60)
    typeEpisode = (await state.get_data())["typeEpisode"]
    numberLastEpisode = str(
        int(await get_last_post_ID(typeEpisode, FTP_SERVER, FTP_LOGIN, FTP_PASSWORD)) + 1
    )  # Используется в контексте
    await download_msg.edit_text(context[language].downloaded)
    await msg.answer(
        context.ask_template[typeEpisode].replace("600", numberLastEpisode),
        reply_markup=keyboards["podcast_handler"][language].cancel,
    )
    await state.set_state(UploadFile.template)


@logger.catch
@router.message(F.text, UploadFile.template)
async def set_template(msg: Message, state: FSMContext, language: str, username: str) -> None:
    #TODO: REFACTORING
    typeEpisode = (await state.get_data())["typeEpisode"]

    if typeEpisode == "main":
        logger.opt(colors=True).debug(f"[<y>{username}</y>]: Choosed main episode")
    elif typeEpisode == "aftershow":
        logger.opt(colors=True).debug(f"[<y>{username}</y>]: Choosed aftershow episode")

    text = msg.text
    info = validate_template(text)
    temp = await msg.answer(context[language].set_tags)

    #TODO: REFACTOR THIS SHIT
    if info is None:
        logger.opt(colors=True).debug(f"[<y>{username}</y>]: Invalid input in tagging")
        return await msg.reply(context[language].invalid_input)

    logger.opt(colors=True).debug(
        f"[<y>{username}</y>]: Started audiotagging {'main' if typeEpisode == 'main' else 'aftershow'} epidose"
    )
    audio_tag(info, typeEpisode)
    new_file_name = f'{info["number"].zfill(4)}_{"rz" if typeEpisode == "main" else "postshow"}_{datetime.now(TIMEZONE).strftime("%d%m%Y")}.mp3'

    logger.opt(colors=True).debug(f"<g>[<y>{username}</y>]: Audiotagging complete succsessful</g>")
    Path(PODCAST_PATH).rename(Path(FILES_PATH) / new_file_name)

    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Upload MP3 file")
    await temp.delete()
    temp = await msg.answer(context[language].done_tag, reply_markup=ReplyKeyboardRemove())

    #TODO: Посмотреть вариант отслеживания загрузки

    await msg.reply_audio(
        FSInputFile(f"{FILES_PATH}/{new_file_name}", new_file_name),
        context[language].done_mp3,
        reply_markup=(
            keyboards["podcast_handler"][language].audioMenuMain
            if typeEpisode == "main"
            else keyboards["podcast_handler"][language].audioMenuPost
        ),
    )
    await temp.delete()
    logger.opt(colors=True).debug(f"<g>[<y>{username}</y>]: MP3 file uploaded</g>")
    await state.clear()
