import os
import shutil
from datetime import datetime, timezone, timedelta
from typing import cast

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter, Text
from aiogram.fsm.context import FSMContext
from aiogram.types import (CallbackQuery, FSInputFile, Message,
                           ReplyKeyboardRemove)
from loguru import logger

from config import (FILES_PATH, FTP_LOGIN, FTP_PASSWORD, FTP_SERVER, LOCAL,
                    PODCAST_PATH)
from forms.uploadFile import UploadFile
from utils.bot_methods import uploadToFTP
from utils.context import context
from utils.dispatcher_filters import ContextButton, IsAdmin, IsPrivate
from utils.keyboards import keyboards
from utils.mp3tagger import audiotag
from utils.validators import validatePath, validateTemplate

timeZone = timezone(timedelta(hours=3))
router = Router(name="podcastHandler")
router.message.filter(IsPrivate, IsAdmin)


@router.message(F.text, CommandStart())
async def start(msg: Message, state: FSMContext, language: str,
                username: str) -> None:
    logger.opt(colors=True).debug(
        f"[<y>{username}</y>]: Called <b>/start</b> command")
    await msg.reply(
        context[language].ask_typeEpisode,
        reply_markup=keyboards["podcastHandler"][language].typeEpisode)
    await state.set_state(UploadFile.typeEpisode)


@router.message(F.text, ContextButton("cancel"), StateFilter(UploadFile))
async def cancel(msg: Message, state: FSMContext, language: str,
                 username: str) -> None:
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Cancel MP3 tagging")
    await msg.reply(context[language].canceled,
                    reply_markup=ReplyKeyboardRemove(remove_keyboard=True))
    await state.clear()


@router.message(F.text, ContextButton(["main_episode", "episode_aftershow"]),
                UploadFile.typeEpisode)
async def getType(msg: Message, state: FSMContext, language: str,
                  username: str) -> None:
    await state.update_data(typeEpisode="main" if msg.text ==
                            context[language].main_episode else "aftershow")
    await state.set_state(UploadFile.mp3)
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Get type of episode")
    typeEpisode = msg.text.lower()  #! context for formatting, don't touch!
    #TODO refactoring this shit (in the future...)
    await msg.reply(context[language].ask_mp3,
                    reply_markup=keyboards["podcastHandler"][language].cancel)


@router.message(UploadFile.mp3, F.audio)
async def getMP3(msg: Message, state: FSMContext, bot: Bot, language: str,
                 username: str) -> None:
    logger.opt(
        colors=True).debug(f"[<y>{username}</y>]: Got MP3, downloading...")
    download_msg = await msg.reply(context[language].got_mp3)
    for item in os.listdir(FILES_PATH):
        if item.endswith(".mp3"):
            os.remove(os.path.join(FILES_PATH, item))
    logger.opt(
        colors=True).debug(f"[<y>{username}</y>]: Deleted previous MP3 files")

    if LOCAL:
        # TODO MORE LOGGING FOR THE GOD OF LOGGING
        from re import findall

        from config import API_TOKEN
        file = await bot.get_file(msg.audio.file_id)
        g = findall(r'\/music\/(.*?)$', str(file.file_path))[0]
        shutil.move(f"/var/lib/telegram-bot-api/{API_TOKEN}/music/{g}",
                    PODCAST_PATH)
    else:
        await bot.download(msg.audio.file_id, PODCAST_PATH, timeout=60)
    await download_msg.edit_text(context[language].downloaded)
    await msg.answer(context.ask_template[(await
                                           state.get_data())["typeEpisode"]],
                     reply_markup=keyboards["podcastHandler"][language].cancel)
    await state.set_state(UploadFile.template)


@router.message(F.text, UploadFile.template)
async def setTemplate(msg: Message, state: FSMContext, language: str,
                      username: str) -> None:
    #TODO get number from site
    #TODO REFACTORING
    typeEpisode = (await state.get_data())["typeEpisode"]

    if typeEpisode == "main":
        logger.opt(
            colors=True).debug(f"[<y>{username}</y>]: Choosed main episode")
    elif typeEpisode == "aftershow":
        logger.opt(colors=True).debug(
            f"[<y>{username}</y>]: Choosed aftershow episode")

    text = msg.text
    info = validateTemplate(typeEpisode, text)
    temp = await msg.answer(context[language].set_tags)

    # TODO REFACTOR THIS SHIT
    if info == None:
        logger.opt(colors=True).debug(
            f"[<y>{username}</y>]: Invalid input in tagging")
        return await msg.reply(context[language].invalid_input)

    logger.opt(colors=True).debug(
        f"[<y>{username}</y>]: Started audiotagging {'main' if typeEpisode == 'main' else 'aftershow'} epidose"
    )
    audiotag(info, typeEpisode)
    new_file_name = f'{info["number"].zfill(4)}_{"rz" if typeEpisode == "main" else "postshow"}_{datetime.now(timeZone).strftime("%d%m%Y")}.mp3'

    logger.opt(colors=True).debug(
        f"<g>[<y>{username}</y>]: Audiotagging complete succsessful</g>")
    os.rename(PODCAST_PATH,
              f"{FILES_PATH}/{new_file_name}")  #TODO USE AIOFILES

    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Upload MP3 file")
    temp = await temp.edit_text(context[language].done_tag, reply_markup=None)
    #TODO Посмотреть вариант отслеживания загрузки

    await msg.reply_audio(
        FSInputFile(f"{FILES_PATH}/{new_file_name}", new_file_name),
        context[language].done_mp3,
        reply_markup=keyboards["podcastHandler"][language].audioMenu)
    #TODO add inline button for upload
    await temp.delete()
    logger.opt(
        colors=True).debug(f"<g>[<y>{username}</y>]: MP3 file uploaded</g>")
    await state.clear()


#TODO LOGGING and refactoring (in future)
@router.callback_query(Text("audioMenu"))
async def audioMenu(callback: CallbackQuery, language: str, username: str):
    await callback.answer()
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: AudioMenu")

    return await callback.message.edit_reply_markup(
        "Операции с подкастом:",
        reply_markup=keyboards["podcastHandler"][language].audioMenu)


#TODO LOGGING and refactoring (in future)
@router.callback_query(Text("FTPMenu"))
async def FTPMenu(callback: CallbackQuery, language: str, username: str):
    await callback.answer()
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: FTPMenu")
    return await callback.message.edit_reply_markup(
        reply_markup=keyboards["podcastHandler"][language].FTPMenu)






#TODO LOGGING and refactoring (in future)
@router.callback_query(Text("FTP_upload"))
async def uploadFTP(callback: CallbackQuery, language: str, username: str):
    await callback.answer()
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: FTP_upload")


    await uploadToFTP(f"{FILES_PATH}/{callback.message.audio.file_name}",
                      callback.message.audio.file_name, FTP_SERVER, FTP_LOGIN,
                      FTP_PASSWORD)
    return await callback.message.answer(
        "Файл успешно загружен на FTP"
    )  #TODO context #TODO Проверку бы добавить...


#TODO послешоу в отдельную папку