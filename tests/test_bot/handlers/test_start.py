########################################################
#                                                      #
#   Note:                                              #
#                                                      #
#   - I'm not looking here. Here is a pure shitcode.   #
#   - I don't understand tests.                        #
#   - I'm learning this shit.                          #
#                                                      #
########################################################


import pytest
from typing import Optional, Union
from aiogram.enums import ChatType
from aiogram.filters import Command
from config import PODCAST_PATH
from aiogram_tests import MockedRequester
from aiogram_tests.handler import MessageHandler
from aiogram_tests.types.dataset import CHAT, MESSAGE, USER, MESSAGE_WITH_AUDIO, AUDIO

from aiogram.methods import SendMessage, EditMessageText
from config import ADMINS
from handlers.start_handler import *
from keyboards import reply
from utils.dispatcher_filters import ContextButton, IsAdmin
from forms.uploadFile import UploadFile
from unittest.mock import AsyncMock

from aiogram.filters import BaseFilter
import responses
from aiogram.types import Message

#import context  #TODO use this

class ChatTypeFilter(BaseFilter):
    def __init__(self, chat_type: Union[str, list]):
        self.chat_type = chat_type

    async def __call__(self, message: Message) -> bool:
        if isinstance(self.chat_type, str):
            return message.chat.type == self.chat_type
        else:
            return message.chat.type in self.chat_type
        

ADMIN = USER.as_object(first_name=ADMINS[0], username=ADMINS[0])
PRIVATE_CHAT = CHAT.as_object(type=ChatType.PRIVATE)
GROUP_CHAT = CHAT.as_object(type=ChatType.GROUP)


@pytest.mark.asyncio
async def test_start_01(): #! ADMIN
    HANDLER = start
    TEXT = "/start"
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [Command(commands=["start"]), ChatTypeFilter(ChatType.PRIVATE), IsAdmin]
    mh = MessageHandler(HANDLER, *FILTRES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(text=TEXT, from_user = FROM_USER, chat=FROM_CHAT))
    answer_message = calls.send_message.fetchone()
    assert answer_message.text == f'Привет <b>{ADMINS[0]}</b>, что мы добавляем?'
    
    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == 'UploadFile:typeEpisode'

    #! KEYBOARD CHECK
    assert answer_message.reply_markup == reply.ru.typeEpisode


@pytest.mark.asyncio
async def test_start_02(): #! USER, PRIVATE CHAT
    HANDLER = start
    TEXT = "/start"
    FROM_USER = USER
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [Command(commands=["start"]), ChatTypeFilter(ChatType.PRIVATE), IsAdmin]
    mh = MessageHandler(HANDLER, *FILTRES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(text=TEXT, from_user = FROM_USER, chat=FROM_CHAT))
    assert len(calls._get_attributes()) == 0


@pytest.mark.asyncio
async def test_start_03(): #! ADMIN, NOT PRIVATE CHAT
    HANDLER = start
    TEXT = "/start"
    FROM_USER = ADMIN
    FROM_CHAT = GROUP_CHAT
    FILTRES = [ChatTypeFilter(ChatType.PRIVATE), IsAdmin, Command(commands=["start"])]
    mh = MessageHandler(HANDLER, *FILTRES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(text=TEXT, from_user = FROM_USER, chat=FROM_CHAT))
    assert len(calls._get_attributes()) == 0


@pytest.mark.asyncio
async def test_start_04(): #! NOT ADMIN, NOT PRIVATE CHAT
    HANDLER = start
    TEXT = "/start"
    FROM_USER = USER
    FROM_CHAT = GROUP_CHAT
    FILTRES = [Command(commands=["start"]), ChatTypeFilter(ChatType.PRIVATE), IsAdmin]
    mh = MessageHandler(HANDLER, *FILTRES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(text=TEXT, from_user = FROM_USER, chat=FROM_CHAT))
    assert len(calls._get_attributes()) == 0


@pytest.mark.asyncio
async def test_start_05(): #! NOT ADMIN, NOT PRIVATE CHAT, WITH STATE
    HANDLER = start
    TEXT = "/start"
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [Command(commands=["start"]), ChatTypeFilter(ChatType.PRIVATE), IsAdmin]
    mh = MessageHandler(HANDLER, *FILTRES, state=UploadFile.mp3)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(text=TEXT, from_user = FROM_USER, chat=FROM_CHAT))
    answer_message = calls.send_message.fetchone()
    assert answer_message.text == f'Привет <b>{ADMINS[0]}</b>, что мы добавляем?'
    
    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == 'UploadFile:typeEpisode'

    #! KEYBOARD CHECK
    assert answer_message.reply_markup == reply.ru.typeEpisode


@pytest.mark.asyncio
async def test_cancel():
    HANDLER = cancel
    TEXT = "/cancel"
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [Command(commands=["cancel"]), ChatTypeFilter(ChatType.PRIVATE), IsAdmin, F.text]
    mh = MessageHandler(HANDLER, *FILTRES, state=UploadFile.mp3)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(text=TEXT, from_user = FROM_USER, chat=FROM_CHAT))
    answer_message = calls.send_message.fetchone()
    assert answer_message.text == "Отмененно"
    
    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == None

    #! KEYBOARD CHECK
    assert answer_message.reply_markup["remove_keyboard"]


async def _getType(TEXT: str, stateData: dict):
    HANDLER = getType
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    stateName = "UploadFile:mp3"
    FILTRES = [F.text, ContextButton(["main_episode", "episode_aftershow"]), ChatTypeFilter(ChatType.PRIVATE), IsAdmin]
    mh = MessageHandler(HANDLER, *FILTRES, state=UploadFile.typeEpisode)
    typeEpisode = TEXT.lower()

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(text=TEXT, from_user = FROM_USER, chat=FROM_CHAT))
    answer_message = calls.send_message.fetchone()
    assert answer_message.text == f"Загружаем <b>{typeEpisode}</b>. Ожидаю mp3"
    
    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == stateName
    assert (await state.get_data()) == stateData

    #! KEYBOARD CHECK
    assert answer_message.reply_markup == keyboards["reply"]["ru"].cancel


@pytest.mark.asyncio
async def test_getType_01(): #! Main episode
    TEXT = "Основной эпизод"
    stateData = {"typeEpisode": "main"}
    await _getType(TEXT, stateData)


@pytest.mark.asyncio
async def test_getType_02(): #! Aftershow episode
    TEXT = "Эпизод послешоу"
    stateData = {"typeEpisode": "aftershow"}
    await _getType(TEXT, stateData)


@pytest.mark.asyncio
async def _getMP3(stateData: dict):
    HANDLER = getMP3
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    stateName = "UploadFile:template"
    FILTRES = [IsPrivate, UploadFile.mp3, F.audio, IsAdmin]
    mh = MessageHandler(HANDLER, *FILTRES, state=UploadFile.mp3, state_data = stateData)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    mh.bot.download = AsyncMock(return_value=None)
    file_path = "files/test.mp3"
    request.add_result_for(SendMessage, ok=True, result = MESSAGE.as_object(message_id=12346))
    calls = await request.query(message=MESSAGE_WITH_AUDIO.as_object(from_user = FROM_USER, chat=FROM_CHAT, AUDIO=AUDIO.as_object(file_path = file_path)))
    answer_message = calls.edit_message_text.fetchone()
    assert answer_message.text == 'MP3 загружено! Теперь пришли описание эпизода в соответствии с шаблоном ниже, ничего не меняя, кроме значений полей:'

    answer_messages = calls.send_message.fetchall()
    assert answer_messages[0].text == 'Вижу MP3, начинаю загрузку'

    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == stateName
    assert await state.get_data() == stateData

    #TODO add section for file
    
    assert answer_messages[1].text == context.ask_template[stateData["typeEpisode"]]    

    #! KEYBOARD CHECK
    assert answer_messages[1].reply_markup == keyboards["reply"]["ru"].cancel


#TODO ADD FOR LOCAL
@pytest.mark.asyncio
async def test_getMP3_01():
    stateData = {"typeEpisode": "main"}
    await _getMP3(stateData)


@pytest.mark.asyncio
async def test_getMP3_02():
    stateData = {"typeEpisode": "aftershow"}
    await _getMP3(stateData)


#TODO ADD BAD TEST
async def _setTemplate(stateData: dict, text: str):
    HANDLER = setTemplate
    TEXT = text
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [F.text, ChatTypeFilter(ChatType.PRIVATE), IsAdmin]
    mh = MessageHandler(HANDLER, *FILTRES, state=UploadFile.template, state_data=stateData)
    
    #! CREATE MP3 FILE FOR BOT
    import os
    from config import FILES_PATH
    for item in os.listdir(FILES_PATH):
        if item.endswith(".mp3"):
            os.remove(os.path.join(FILES_PATH, item))
    with open(PODCAST_PATH, "wb") as f: #TODO USE AIOFILES
        f.write(b"HELLO WORLD, IT'S TEST!")

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    request.add_result_for(SendMessage, ok=True, result = MESSAGE.as_object(message_id=12346))
    request.add_result_for(EditMessageText, ok=True, result = MESSAGE.as_object(message_id=12346))
    calls = await request.query(message=MESSAGE.as_object(text=TEXT, from_user = FROM_USER, chat=FROM_CHAT))
    edited_message = calls.edit_message_text.fetchone()
    answer_messages = calls.send_message.fetchone()
    audio_message = calls.send_audio.fetchone()
    assert answer_messages.text == "Проставляем теги"
    assert edited_message.text == "Теги проставлены.\nЗагрузка началась, подождите около 5-10 минут"
    assert audio_message.caption == "Вот твой готовый файл!"
    assert calls.delete_message.fetchone()

    #! FILE CHECK
    import re
    
    res = "" #TODO REFACTOR THIS
    for i in [i for i in os.listdir(FILES_PATH) if i.endswith(".mp3")]:
        d = re.findall("\d{4,}_(rz|postshow)_\d{8,}.mp3", i)
        if len(d) > 0:
            res = i
            break
    assert res != ""
    with open(f"{FILES_PATH}/{res}", "rb") as f:
        assert b"HELLO WORLD, IT'S TEST!" == f.read()
    os.remove(f"{FILES_PATH}/{res}")

    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == None

    #! KEYBOARD CHECK
    assert audio_message.reply_markup["remove_keyboard"]


@pytest.mark.asyncio
async def test_setTemplate_01():
    text = context.ask_template["main"]
    stateData = {"typeEpisode": "main"}
    await _setTemplate(stateData, text = text)


@pytest.mark.asyncio
async def test_setTemplate_02():
    text = context.ask_template["aftershow"]
    stateData = {"typeEpisode": "aftershow"}
    await _setTemplate(stateData, text = text)