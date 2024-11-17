import pytest
from aiogram_tests.types.dataset import MESSAGE, USER
from aiogram.filters import Command
from app.handlers.podcast_handler import start
from app.services.context import context
from app.forms.upload_file import UploadFile
from app.config import LANGUAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_of_test"])
@pytest.mark.parametrize("language", LANGUAGES)
async def test_start_command(language, username, handler_factory, bot_factory, state_context_factory):
    # Настройка обработчика и команды start
    handler_func = start
    command = Command(commands=["start"])

    # Создание бота и контекста с использованием фабрик
    handler = handler_factory(handler_func, command=command)
    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)
    msg = MESSAGE.as_object(text="/start", from_user=user)

    # Выполняем команду /start
    calls = await bot.query(message=msg)
    state_context = await state_context_factory(handler, message=msg)

    # Проверка отправленного сообщения
    assert len(calls.send_message) == 1
    sent_message = calls.send_message.fetchone()
    expected_text = context[language].ask_typeEpisode
    assert sent_message.text == expected_text

    # Проверка установки состояния FSM
    assert (await state_context.get_state()) == UploadFile.typeEpisode
