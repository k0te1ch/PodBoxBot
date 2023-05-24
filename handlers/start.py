from aiogram.dispatcher.filters import CommandStart, Text, ContentTypeFilter
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, ContentType

from datetime import datetime
from re import findall, MULTILINE
import os
from bot import dp, context, keyboards
from config import API_TOKEN, FILES_PATH, PODCAST
from forms.uploadFile import UploadFile
from utils.mp3tagger import audiotag_RZ, audiotag_PS
from utils.HTTP_methods import downloadFile
from utils.dispatcher_filters import ContextButton, IsPrivate, IsAdmin
from loguru import logger


@dp.message_handler(CommandStart(), IsPrivate, IsAdmin)
async def start(msg, language):
    await UploadFile.typeEpisode.set()
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Called <b>/start</b> command")
    return await msg.reply(context[language].ask_typeEpisode, reply_markup=keyboards["reply"][language].typeEpisode)


@dp.message_handler(ContextButton(["main_episode", "episode_aftershow"]), IsPrivate, IsAdmin, state=UploadFile.typeEpisode)
async def getType(msg, language, state):
    async with state.proxy() as data:
        data['typeEpisode'] = "main" if msg.text == context[language].main_episode else "aftershow"
    await UploadFile.next()
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Get type of episode")
    typeEpisode = msg.text.lower()
    return await msg.reply(context[language].ask_mp3, reply_markup=keyboards["reply"][language].cancel)


@dp.message_handler(IsPrivate, content_types=ContentType.AUDIO, state=UploadFile.mp3)
async def getMP3(msg, language, state):
    await UploadFile.next()
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Got MP3, downloading...")
    download_msg = await msg.reply(context[language].got_mp3)
    for item in os.listdir(FILES_PATH):
        if item.endswith(".mp3"):
            os.remove(os.path.join(FILES_PATH, item))
            logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Deleted previous MP3 files")
    await downloadFile(str(await msg.audio.get_url()).replace(f"/var/lib/telegram-bot-api/{API_TOKEN}", ""), PODCAST)
    await download_msg.edit_text(context[language].downloaded)
    async with state.proxy() as data:
        template = context[language].ask_template_rz if data["typeEpisode"] == "main" else context[language].ask_template_ps
    return await msg.answer(template, reply_markup=keyboards["reply"][language].cancel)

@dp.message_handler(IsPrivate, state=UploadFile.template)
async def setTemplate(msg, state, language):
    #TODO get number from site
    #TODO Validate and parsing template
    async with state.proxy() as data:
        typeEpisode = data["typeEpisode"]
    
    if typeEpisode == "main":
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Choosed main episode")
        reg = r"Number: (\d+)\nTitle: (.*?)\nComment: (.*?)\nChapters: \|\n(.*?)$"
    elif typeEpisode == "aftershow":
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Choosed aftershow episode")
        reg = r"Number: (\d+)\nTitle: (.*?)\nComment: (.*?)$"

    text = msg.text
    result = findall(reg, text, MULTILINE)

    if len(result) < 1 or ((typeEpisode == "main" and len(result[0]) != 4) or (typeEpisode == "aftershow" and len(result[0]) != 3)):
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Invalid input in tagging")
        return await msg.reply(context[language].invalid_input)
    
    result = result[0]
    number = f"0{result[0]}" if int(result[0]) < 1000 else str(result[0])
    
    temp = await msg.answer("Проставляем теги")
    async with state.proxy() as data:
        typeEpisode = data["typeEpisode"]
    
    if typeEpisode == "main":
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Started audiotagging main episode")
        #TODO REFACTORING CHAPTERS AND AUDIOTAG
        audiotag_RZ(number = number, name = result[1], text = result[2], chapters = text[text.find("Chapters: |"):].splitlines()[1:])
        new_file_name = f'{number}_rz_{datetime.now().strftime("%d%m%Y")}.mp3'
    else:
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Started audiotagging aftershow epidose")
        #TODO REFACTORING CHAPTERS AND AUDIOTAG
        audiotag_PS(number = number, name = result[1], text = result[2])
        new_file_name = f'{number}_ps_{datetime.now().strftime("%d%m%Y")}.mp3'
    
    logger.opt(colors=True).debug(f"<g>[<y>{msg.from_user.username}</y>]: Audiotagging complete succsessful</g>")
    os.rename(PODCAST, f"{FILES_PATH}/{new_file_name}")
    await state.finish()
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Upload MP3 file")
    temp = await temp.edit_text("Теги проставлены.\nЗагрузка началась, подождите около 5 минут")
    await msg.reply_audio(open(f"{FILES_PATH}/{new_file_name}", "rb"), context[language].done_mp3, reply_markup=ReplyKeyboardRemove())
    await temp.delete()
    logger.opt(colors=True).debug(f"<g>[<y>{msg.from_user.username}</y>]: MP3 file uploaded</g>")
    return


@dp.message_handler(ContextButton("cancel"), IsPrivate, IsAdmin, state=UploadFile.all_states)
async def cancel(msg, state, language):
    await state.finish()
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Cancel MP3 tagging")
    return await msg.reply(context[language].register_canceled, reply_markup=ReplyKeyboardRemove())