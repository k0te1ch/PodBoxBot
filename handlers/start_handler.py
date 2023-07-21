import shutil
from aiogram import Bot
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, ContentType
from aiogram.types import FSInputFile

from datetime import datetime
from re import findall, MULTILINE
from aiogram.fsm.context import FSMContext
import os
from utils.keyboards import keyboards
from utils.context import context
from config import API_TOKEN, FILES_PATH, PODCAST, LOCAL, PODCAST_PATH
from forms.uploadFile import UploadFile
from utils.mp3tagger import audiotag_RZ, audiotag_PS, audiotag
from utils.validators import validatePath, validateTemplate
#from utils.HTTP_methods import downloadFile
from utils.dispatcher_filters import ContextButton, IsPrivate, IsAdmin
from loguru import logger
from aiogram import Router
from aiogram import F


router = Router()
router.message.filter(IsPrivate, IsAdmin
)

@router.message(F.text, CommandStart())
async def start(msg: Message, state: FSMContext) -> None:
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Called <b>/start</b> command")
    await msg.reply(context["ru"].ask_typeEpisode, reply_markup=keyboards["reply"]["ru"].typeEpisode)
    await state.set_state(UploadFile.typeEpisode)

@router.message(F.text, ContextButton("cancel"), UploadFile)
async def cancel(msg: Message, state: FSMContext) -> None:
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Cancel MP3 tagging")
    await msg.reply(context["ru"].canceled, reply_markup=ReplyKeyboardRemove())
    await state.clear()


@router.message(F.text, ContextButton(["main_episode", "episode_aftershow"]), UploadFile.typeEpisode)
async def getType(msg: Message, state: FSMContext) -> None:
    await state.update_data(typeEpisode = "main" if msg.text == context["ru"].main_episode else "aftershow")
    await state.set_state(UploadFile.mp3)
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Get type of episode")
    typeEpisode = msg.text.lower() #! context for formatting, don't touch!
    #TODO refactoring this shit (in the future...)
    await msg.reply(context["ru"].ask_mp3, reply_markup=keyboards["reply"]["ru"].cancel)


@router.message(UploadFile.mp3, F.audio)
async def getMP3(msg: Message, state: FSMContext, bot: Bot) -> None:
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Got MP3, downloading...")
    download_msg = await msg.reply(context["ru"].got_mp3)
    for item in os.listdir(FILES_PATH):
        if item.endswith(".mp3"):
            os.remove(os.path.join(FILES_PATH, item))
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Deleted previous MP3 files")

    if LOCAL:
        # TODO MORE LOGGING FOR THE GOD OF LOGGING
        g = findall('\/music\/(.*?)$', str(await msg.audio.get_url()))[0]
        shutil.move(f"/var/lib/telegram-bot-api/{API_TOKEN}/music/{g}", PODCAST_PATH)
    else:
        #await downloadFile(str(await msg.audio.get_url()).replace(f"/var/lib/telegram-bot-api/{API_TOKEN}", ""), PODCAST_PATH)
        await bot.download(msg.audio.file_id, PODCAST_PATH)
    await download_msg.edit_text(context["ru"].downloaded)
    await msg.answer(context.ask_template[(await state.get_data())["typeEpisode"]], reply_markup=keyboards["reply"]["ru"].cancel)
    await state.set_state(UploadFile.template)


@router.message(F.text, UploadFile.template)
async def setTemplate(msg: Message, state: FSMContext) -> None:
    #TODO context
    #TODO get number from site
    #TODO REFACTORING
    typeEpisode = (await state.get_data())["typeEpisode"]
    
    if typeEpisode == "main":
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Choosed main episode")
    elif typeEpisode == "aftershow":
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Choosed aftershow episode")

    text = msg.text
    info = validateTemplate(typeEpisode, text)
    temp = await msg.answer("Проставляем теги")
    
    # TODO REFACTOR THIS SHIT
    if info == None:
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Invalid input in tagging")
        return await msg.reply(context["ru"].invalid_input)
    
    """
    if typeEpisode == "main":
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Started audiotagging main episode")
        #TODO REFACTORING AUDIOTAG
        audiotag_RZ(info)
        new_file_name = f'{info["number"].zfill(4)}_rz_{datetime.now().strftime("%d%m%Y")}.mp3'
    else:
        logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Started audiotagging aftershow epidose")
        #TODO REFACTORING AUDIOTAG
        audiotag_PS(info)
        new_file_name = f'{info["number"].zfill(4)}_postshow_{datetime.now().strftime("%d%m%Y")}.mp3'
    """

    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Started audiotagging {'main' if typeEpisode == 'main' else 'aftershow'} epidose")
    audiotag(info, typeEpisode)
    new_file_name = f'{info["number"].zfill(4)}_{"rz" if typeEpisode == "main" else "postshow"}_{datetime.now().strftime("%d%m%Y")}.mp3'
    
    logger.opt(colors=True).debug(f"<g>[<y>{msg.from_user.username}</y>]: Audiotagging complete succsessful</g>")
    os.rename(PODCAST_PATH, f"{FILES_PATH}/{new_file_name}") #TODO USE AIOFILES

    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Upload MP3 file") 
    temp = await temp.edit_text("Теги проставлены.\nЗагрузка началась, подождите около 2-5 минут") #TODO ADD THIS TO CONTEXT
    #TODO Посмотреть вариант отслеживания загрузки

    await msg.reply_audio(FSInputFile(f"{FILES_PATH}/{new_file_name}", new_file_name), context["ru"].done_mp3, reply_markup=ReplyKeyboardRemove())
    #TODO add inline button for upload
    await temp.delete()
    logger.opt(colors=True).debug(f"<g>[<y>{msg.from_user.username}</y>]: MP3 file uploaded</g>")
    await state.clear()
