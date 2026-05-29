from unittest.mock import AsyncMock, patch

import pytest
from aiogram_tests.requester import Calls
from aiogram_tests.types.dataset import CALLBACK_QUERY, MESSAGE, USER
from app.config import LANGUAGES
from app.handlers.audio_handler import forward_verify
from app.services.keyboards import keyboards


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_user"])
@pytest.mark.parametrize("language", LANGUAGES)
async def test_forward_verify(callback_handler_factory, bot_factory, username, language):
    # Создаем мок обработчика
    handler = callback_handler_factory(forward_verify)
    bot = await bot_factory(handler)

    # Мокаем объекты пользователя и сообщения
    user = USER.as_object(id=123, username=username, language_code=language)
    message = MESSAGE.as_object(message_id=1, from_user=user, text="Test message")
    callback_query = CALLBACK_QUERY.as_object(
        id="1", from_user=user, message=message, data="fwd_verify", chat_instance="instance"
    )

    # Мокаем ответ callback_query.answer и проверяем работу обработчика
    with patch("app.handlers.audio_handler.CallbackQuery.answer", new=AsyncMock()) as mock_answer:
        calls: Calls = await bot.query(callback_query)

        # Проверяем, что answer вызван с правильными параметрами
        mock_answer.assert_called_once_with(
            text="Вы выбрали переслать сообщение в чат, переслать?", show_alert=True, cache_time=60
        )

        # Проверяем, что edit_reply_markup был вызван с правильной клавиатурой
        edit_reply_markup_call = calls.edit_message_reply_markup.fetchone()
        assert edit_reply_markup_call.reply_markup == keyboards["podcast_handler"][language].verify
