import pytest
from aiogram_tests.types.dataset import MESSAGE, USER
from aiogram.types import ReplyKeyboardRemove
from app.handlers.podcast_handler import cancel
from app.services.context import context
from app.forms.upload_file import UploadFile
from app.filters.dispatcher_filters import ContextButton
from app.config import LANGUAGES


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_user", "test_of_test"])
@pytest.mark.parametrize("language", LANGUAGES)
async def test_cancel_command(language, username, handler_factory, bot_factory, state_context_factory):
    # Настройка обработчика и команды для cancel
    handler_func = cancel
    command = ContextButton("cancel")
    state = UploadFile.typeEpisode

    # Создание обработчика, бота и контекста с использованием фабрик
    handler = handler_factory(handler_func, command=command, state=state)
    bot = await bot_factory(handler)
    user = USER.as_object(username=username, language_code=language)
    msg = MESSAGE.as_object(text="Отмена", from_user=user)

    # Выполняем обработчик cancel
    calls = await bot.query(message=msg)
    state_context = await state_context_factory(handler, message=msg)

    # Проверка отправленного сообщения и сброса состояния FSM
    assert len(calls.send_message) == 1
    sent_message = calls.send_message.fetchone()
    expected_text = context[language].canceled
    assert sent_message.text == expected_text
    assert sent_message.reply_markup == ReplyKeyboardRemove(remove_keyboard=True)
    assert (await state_context.get_state()) is None
