import shutil
from aiogram.dispatcher.filters import CommandStart, Text, ContentTypeFilter
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, ContentType

from datetime import datetime
from re import findall, MULTILINE
import os
from bot import dp, context, keyboards
from config import API_TOKEN, FILES_PATH, PODCAST, LOCAL, PODCAST_PATH
from forms.uploadFile import UploadFile
from utils.mp3tagger import audiotag_RZ, audiotag_PS
from utils.validators import validatePath, validateTemplate
from utils.HTTP_methods import downloadFile
from utils.dispatcher_filters import ContextButton, IsPrivate, IsAdmin
from loguru import logger


@dp.message_handler(CommandStart(), IsPrivate, IsAdmin)
async def start(msg, language):
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Called <b>/start</b> command")
    await msg.reply(context[language].ask_typeEpisode, reply_markup=keyboards["reply"][language].typeEpisode)
    return await UploadFile.typeEpisode.set()

@dp.message_handler(ContextButton("cancel"), IsPrivate, IsAdmin, state=UploadFile.all_states)
async def cancel(msg, state, language):
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Cancel MP3 tagging")
    await msg.reply(context[language].register_canceled, reply_markup=ReplyKeyboardRemove())
    return await state.finish()


@dp.message_handler(ContextButton(["main_episode", "episode_aftershow"]), IsPrivate, IsAdmin, state=UploadFile.typeEpisode)
async def getType(msg, language, state):
    async with state.proxy() as data:
        data['typeEpisode'] = "main" if msg.text == context[language].main_episode else "aftershow"
    await UploadFile.next()
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Get type of episode")
    typeEpisode = msg.text.lower() # context for formatting, don't touch!
    return await msg.reply(context[language].ask_mp3, reply_markup=keyboards["reply"][language].cancel)


@dp.message_handler(IsPrivate, content_types=ContentType.AUDIO, state=UploadFile.mp3)
async def getMP3(msg, language, state):
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Got MP3, downloading...")
    download_msg = await msg.reply(context[language].got_mp3)
    for item in os.listdir(FILES_PATH):
        if item.endswith(".mp3"):
            os.remove(os.path.join(FILES_PATH, item))
            logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Deleted previous MP3 files")

    if LOCAL:
        # TODO MORE LOGGING FOR THE GOD OF LOGGING
        g = findall('\/music\/(.*?)$', str(await msg.audio.get_url()))[0]
        shutil.move(f"/var/lib/telegram-bot-api/{API_TOKEN}/music/{g}", PODCAST_PATH)
    else:
        await downloadFile(str(await msg.audio.get_url()).replace(f"/var/lib/telegram-bot-api/{API_TOKEN}", ""), PODCAST_PATH)

    await download_msg.edit_text(context[language].downloaded)
    async with state.proxy() as data:
        template = context.ask_template_rz if data["typeEpisode"] == "main" else context.ask_template_ps
    await msg.answer(template, reply_markup=keyboards["reply"][language].cancel)
    return await UploadFile.next()

@dp.message_handler(IsPrivate, state=UploadFile.template)
async def setTemplate(msg, state, language):
    #TODO get number from site
    #TODO REFACTORING
    async with state.proxy() as data:
        typeEpisode = data["typeEpisode"]
    
    if typeEpisode == "main":
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Choosed main episode")
    elif typeEpisode == "aftershow":
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Choosed aftershow episode")

    text = msg.text
    info = validateTemplate(typeEpisode, text)
    temp = await msg.answer("Проставляем теги")
    async with state.proxy() as data:
        typeEpisode = data["typeEpisode"]
    
    # TODO REFACTOR THIS SHIT
    info = validateTemplate(typeEpisode, text)
    if info == None:
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Invalid input in tagging")
        return await msg.reply(context[language].invalid_input)
    
    if typeEpisode == "main":
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Started audiotagging main episode")
        #TODO REFACTORING AUDIOTAG
        audiotag_RZ(info)
        new_file_name = f'{info["number"]}_rz_{datetime.now().strftime("%d%m%Y")}.mp3'
    else:
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Started audiotagging aftershow epidose")
        #TODO REFACTORING AUDIOTAG
        audiotag_PS(info)
        new_file_name = f'{info["number"]}_postshow_{datetime.now().strftime("%d%m%Y")}.mp3'
    
    logger.opt(colors=True).debug(f"<g>[<y>{msg.from_user.username}</y>]: Audiotagging complete succsessful</g>")
    os.rename(PODCAST_PATH, f"{FILES_PATH}/{new_file_name}")
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Upload MP3 file")
    temp = await temp.edit_text("Теги проставлены.\nЗагрузка началась, подождите около 5 минут")
    await msg.reply_audio(open(f"{FILES_PATH}/{new_file_name}", "rb"), context[language].done_mp3, reply_markup=ReplyKeyboardRemove())
    #TODO add inline button for upload
    await temp.delete()
    logger.opt(colors=True).debug(f"<g>[<y>{msg.from_user.username}</y>]: MP3 file uploaded</g>")
    return await state.finish()