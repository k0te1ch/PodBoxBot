########################################################
#                                                      #
#   Note:                                              #
#                                                      #
#   - I'm not looking here. Here is a pure shitcode.   #
#   - I don't understand tests.                        #
#   - I'm learning this shit.                          #
#                                                      #
########################################################

from unittest.mock import AsyncMock

import pytest
from aiogram.enums import ChatType
from aiogram.filters import Command, StateFilter
from aiogram.methods import EditMessageText, SendMessage
from aiogram_tests import MockedRequester
from aiogram_tests.handler import MessageHandler
from aiogram_tests.types.dataset import (AUDIO, CHAT, MESSAGE,
                                         MESSAGE_WITH_AUDIO, USER)

from config import ADMINS, PODCAST_PATH
from forms.uploadFile import UploadFile
from handlers.middlewares import GeneralMiddleware
from handlers.podcastHandler import *
from keyboards import podcastHandler
from utils.dispatcher_filters import ContextButton, IsAdmin, IsPrivate

ADMIN = USER.as_object(first_name=ADMINS[0], username=ADMINS[0])
PRIVATE_CHAT = CHAT.as_object(type=ChatType.PRIVATE)
GROUP_CHAT = CHAT.as_object(type=ChatType.GROUP)


@pytest.mark.asyncio
async def test_start_01() -> None:  #! ADMIN, PRIVATE CHAT, WITHOUT CHAT
    HANDLER = start
    TEXT = "/start"
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [Command(commands=["start"]), IsPrivate, IsAdmin]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER, *FILTRES, dp_middlewares=MIDDLEWARES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(
        text=TEXT, from_user=FROM_USER, chat=FROM_CHAT))
    answer_message = calls.send_message.fetchone()
    assert answer_message.text == f'Привет <b>{ADMINS[0]}</b>, что мы добавляем?'

    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == 'UploadFile:typeEpisode'

    #! KEYBOARD CHECK
    assert answer_message.reply_markup == podcastHandler.ru.typeEpisode


@pytest.mark.asyncio
async def test_start_02() -> None:  #! USER, PRIVATE CHAT
    HANDLER = start
    TEXT = "/start"
    FROM_USER = USER
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [Command(commands=["start"]), IsPrivate, IsAdmin]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER, *FILTRES, dp_middlewares=MIDDLEWARES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(
        text=TEXT, from_user=FROM_USER, chat=FROM_CHAT))
    assert len(calls._get_attributes()) == 0


@pytest.mark.asyncio
async def test_start_03() -> None:  #! ADMIN, NOT PRIVATE CHAT
    HANDLER = start
    TEXT = "/start"
    FROM_USER = ADMIN
    FROM_CHAT = GROUP_CHAT
    FILTRES = [IsPrivate, IsAdmin, Command(commands=["start"])]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER, *FILTRES, dp_middlewares=MIDDLEWARES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(
        text=TEXT, from_user=FROM_USER, chat=FROM_CHAT))
    assert len(calls._get_attributes()) == 0


@pytest.mark.asyncio
async def test_start_04() -> None:  #! NOT ADMIN, NOT PRIVATE CHAT
    HANDLER = start
    TEXT = "/start"
    FROM_USER = USER
    FROM_CHAT = GROUP_CHAT
    FILTRES = [Command(commands=["start"]), IsPrivate, IsAdmin]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER, *FILTRES, dp_middlewares=MIDDLEWARES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(
        text=TEXT, from_user=FROM_USER, chat=FROM_CHAT))
    assert len(calls._get_attributes()) == 0


@pytest.mark.asyncio
async def test_start_05() -> None:  #! NOT ADMIN, NOT PRIVATE CHAT, WITH STATE
    HANDLER = start
    TEXT = "/start"
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [Command(commands=["start"]), IsPrivate, IsAdmin]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER,
                        *FILTRES,
                        state=UploadFile.mp3,
                        dp_middlewares=MIDDLEWARES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(
        text=TEXT, from_user=FROM_USER, chat=FROM_CHAT))
    answer_message = calls.send_message.fetchone()
    assert answer_message.text == f'Привет <b>{ADMINS[0]}</b>, что мы добавляем?'

    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == 'UploadFile:typeEpisode'

    #! KEYBOARD CHECK
    assert answer_message.reply_markup == podcastHandler.ru.typeEpisode


@pytest.mark.asyncio
async def test_cancel_01() -> None:
    HANDLER = cancel
    TEXT = "/cancel"
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [Command(commands=["cancel"]), IsPrivate, IsAdmin, F.text]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER,
                        *FILTRES,
                        state=UploadFile.mp3,
                        dp_middlewares=MIDDLEWARES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(
        text=TEXT, from_user=FROM_USER, chat=FROM_CHAT))
    answer_message = calls.send_message.fetchone()
    assert answer_message.text == "Отмененно"

    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == None

    #! KEYBOARD CHECK
    assert answer_message.reply_markup["remove_keyboard"]


@pytest.mark.asyncio
async def test_cancel_02() -> None:
    HANDLER = cancel
    TEXT = "/cancel"
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [
        Command(commands=["cancel"]), IsPrivate, IsAdmin, F.text,
        StateFilter(UploadFile)
    ]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER, *FILTRES, dp_middlewares=MIDDLEWARES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(
        text=TEXT, from_user=FROM_USER, chat=FROM_CHAT))
    assert len(calls._get_attributes()) == 0


async def _getType(TEXT: str, stateData: dict) -> None:
    HANDLER = getType
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    stateName = "UploadFile:mp3"
    FILTRES = [
        F.text,
        ContextButton(["main_episode", "episode_aftershow"]), IsPrivate,
        IsAdmin
    ]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER,
                        *FILTRES,
                        state=UploadFile.typeEpisode,
                        dp_middlewares=MIDDLEWARES)
    typeEpisode = TEXT.lower()

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    calls = await request.query(message=MESSAGE.as_object(
        text=TEXT, from_user=FROM_USER, chat=FROM_CHAT))
    answer_message = calls.send_message.fetchone()
    assert answer_message.text == f"Загружаем <b>{typeEpisode}</b>. Ожидаю mp3"

    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == stateName
    assert (await state.get_data()) == stateData

    #! KEYBOARD CHECK
    assert answer_message.reply_markup == keyboards["podcastHandler"]["ru"].cancel


@pytest.mark.asyncio
async def test_getType_01() -> None:  #! Main episode
    TEXT = "Основной эпизод"
    stateData = {"typeEpisode": "main"}
    await _getType(TEXT, stateData)


@pytest.mark.asyncio
async def test_getType_02() -> None:  #! Aftershow episode
    TEXT = "Эпизод послешоу"
    stateData = {"typeEpisode": "aftershow"}
    await _getType(TEXT, stateData)


@pytest.mark.asyncio
async def _getMP3(stateData: dict) -> None:
    HANDLER = getMP3
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    stateName = "UploadFile:template"
    FILTRES = [IsPrivate, UploadFile.mp3, F.audio, IsAdmin]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER,
                        *FILTRES,
                        state=UploadFile.mp3,
                        state_data=stateData,
                        dp_middlewares=MIDDLEWARES)

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    mh.bot.download = AsyncMock(return_value=None)
    file_path = "files/test.mp3"
    request.add_result_for(SendMessage,
                           ok=True,
                           result=MESSAGE.as_object(message_id=12346))
    calls = await request.query(
        message=MESSAGE_WITH_AUDIO.as_object(from_user=FROM_USER,
                                             chat=FROM_CHAT,
                                             AUDIO=AUDIO.as_object(
                                                 file_path=file_path)))
    answer_message = calls.edit_message_text.fetchone()
    assert answer_message.text == 'MP3 загружено! Теперь пришли описание эпизода в соответствии с шаблоном ниже, ничего не меняя, кроме значений полей:'

    answer_messages = calls.send_message.fetchall()
    assert answer_messages[0].text == 'Вижу MP3, начинаю загрузку'

    #! STATE CHECK
    state = mh.dp.fsm.get_context(mh.bot, user_id=12345678, chat_id=12345678)
    assert await state.get_state() == stateName
    assert await state.get_data() == stateData

    #TODO add section for file

    assert answer_messages[1].text == context.ask_template[
        stateData["typeEpisode"]]

    #! KEYBOARD CHECK
    assert answer_messages[1].reply_markup == keyboards["podcastHandler"]["ru"].cancel


#TODO ADD FOR LOCAL
@pytest.mark.asyncio
async def test_getMP3_01() -> None:
    stateData = {"typeEpisode": "main"}
    await _getMP3(stateData)


@pytest.mark.asyncio
async def test_getMP3_02() -> None:
    stateData = {"typeEpisode": "aftershow"}
    await _getMP3(stateData)


#TODO ADD BAD TEST
async def _setTemplate(stateData: dict, text: str) -> None:
    HANDLER = setTemplate
    TEXT = text
    FROM_USER = ADMIN
    FROM_CHAT = PRIVATE_CHAT
    FILTRES = [F.text, IsPrivate, IsAdmin]
    MIDDLEWARES = [GeneralMiddleware()]
    mh = MessageHandler(HANDLER,
                        *FILTRES,
                        state=UploadFile.template,
                        state_data=stateData,
                        dp_middlewares=MIDDLEWARES)

    #! CREATE MP3 FILE FOR BOT
    import os

    from config import FILES_PATH
    for item in os.listdir(FILES_PATH):
        if item.endswith(".mp3"):
            os.remove(os.path.join(FILES_PATH, item))
    with open(PODCAST_PATH, "wb") as f:  #TODO USE AIOFILES
        f.write(b"HELLO WORLD, IT'S TEST!")

    #! MESSAGE CHECK
    request = MockedRequester(mh)
    request.add_result_for(SendMessage,
                           ok=True,
                           result=MESSAGE.as_object(message_id=12346))
    request.add_result_for(EditMessageText,
                           ok=True,
                           result=MESSAGE.as_object(message_id=12346))
    calls = await request.query(message=MESSAGE.as_object(
        text=TEXT, from_user=FROM_USER, chat=FROM_CHAT))
    edited_message = calls.edit_message_text.fetchone()
    answer_messages = calls.send_message.fetchone()
    audio_message = calls.send_audio.fetchone()
    assert answer_messages.text == "Проставляем теги"
    assert edited_message.text == "Теги проставлены.\nЗагрузка началась, подождите около 2-5 минут"
    assert audio_message.caption == "Вот твой готовый файл!"
    assert calls.delete_message.fetchone()

    #! FILE CHECK
    import re

    res = ""  #TODO REFACTOR THIS
    for i in [i for i in os.listdir(FILES_PATH) if i.endswith(".mp3")]:
        d = re.findall(r"\d{4,}_(rz|postshow)_\d{8,}.mp3", i)
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
    assert "inline_keyboard" in audio_message.reply_markup #TODO add tests


@pytest.mark.asyncio
async def test_setTemplate_01() -> None:
    text = context.ask_template["main"]
    stateData = {"typeEpisode": "main"}
    await _setTemplate(stateData, text=text)


@pytest.mark.asyncio
async def test_setTemplate_02() -> None:
    text = context.ask_template["aftershow"]
    stateData = {"typeEpisode": "aftershow"}
    await _setTemplate(stateData, text=text)
