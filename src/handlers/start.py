from aiogram.dispatcher.filters import CommandStart, Text, ContentTypeFilter
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, ContentType

from datetime import datetime
from re import findall
import os
from main import dp, context
from settings import TOKEN
from forms.uploadFile import UploadFile
from utils.mp3tagger import audiotag
from utils.http_methods import downloadFile
from utils.dispatcher_filters import ContextButton, IsPrivate, IsAdmin


@dp.message_handler(CommandStart(), IsPrivate, IsAdmin)
async def start(msg, user):
    language = msg.from_user.language_code
    if user is not None:
        return await msg.reply(context[language].already_registered)

    await UploadFile.mp3.set()
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(context[language].cancel)
    return await msg.reply(context.welcome, reply_markup=markup)

@dp.message_handler(IsPrivate, content_types=ContentType.AUDIO, state=UploadFile.mp3)
async def getMP3(msg):
    language = msg.from_user.language_code
    await UploadFile.next()
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(context[language].cancel)
    download_msg = await msg.reply(context[language].got_mp3)
    #TODO add src/files
    for item in os.listdir("src/files"):
        if item.endswith(".mp3"):
            os.remove(os.path.join("src/files", item))
    await downloadFile(str(await msg.audio.get_url()).replace(f"/var/lib/telegram-bot-api/{TOKEN}", ""), "src/files/podcast.mp3")
    #TODO add to settings dir to download
    await download_msg.edit_text(context[language].downloaded)
    return await msg.answer(context[language].ask_template, reply_markup=markup)

@dp.message_handler(IsPrivate, state=UploadFile.template)
async def setTemplate(msg, state):
    language = msg.from_user.language_code
    #TODO get number from site

    reg = "Number: (\d+)\nTitle: (.*?)\nComment: (.*?)\nChapters: \|\n(.*?)\n"
    text = msg.text
    result = findall(reg, text)

    if len(result) < 1 or len(result[0]) != 4:
        return await msg.reply(context[language].invalid_input)
    
    result = result[0]
    number = f"0{result[0]}" if int(result[0]) < 1000 else str(result[0])
    
    audiotag(number = number, name = result[1], text = result[2], chapters = text[text.find("Chapters: |"):].splitlines()[1:])

    new_file_name = f'{number}_rz_{datetime.now().strftime("%d%m%Y")}.mp3'
    os.rename("src/files/podcast.mp3", f"src/files/{new_file_name}")
    await state.finish()
    return await msg.reply_audio(open(f"src/files/{new_file_name}", "rb"), context[language].done_mp3, reply_markup=ReplyKeyboardRemove())


@dp.message_handler(ContextButton("cancel", ["ru", "fa"]), IsPrivate, IsAdmin, state=UploadFile.all_states)
async def cancel(msg, state):
    language = msg.from_user.language_code
    await state.finish()
    return await msg.reply(context[language].register_canceled, reply_markup=ReplyKeyboardRemove())