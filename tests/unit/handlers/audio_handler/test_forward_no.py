from unittest.mock import AsyncMock, patch

import pytest
from aiogram_tests.requester import Calls
from aiogram_tests.types.dataset import CALLBACK_QUERY, MESSAGE, USER

from config import LANGUAGES
from handlers.audio_handler import forward_no
from services import keyboards


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["test_user"])
@pytest.mark.parametrize("language", LANGUAGES)
async def test_forward_no(callback_handler_factory, bot_factory, username, language):
    handler = callback_handler_factory(forward_no)
    bot = await bot_factory(handler)

    user = USER.as_object(id=123, username=username, language_code=language)
    message = MESSAGE.as_object(message_id=1, from_user=user, text="Test message")
    callback_query = CALLBACK_QUERY.as_object(id="2", from_user=user, message=message, data="fwd_verify_no")

    # Мокаем метод answer у callback_query и проверяем его вызов с текстом "Отменено"
    with patch("handlers.audio_handler.CallbackQuery.answer", new=AsyncMock()) as mock_answer:
        calls: Calls = await bot.query(callback_query)

        # Проверка, что callback_query.answer вызван с сообщением "Отменено"
        mock_answer.assert_called_once_with("Отменено")

        # Проверка, что edit_message_reply_markup вызван с правильной клавиатурой
        edit_reply_markup_call = calls.edit_message_reply_markup.fetchone()
        assert edit_reply_markup_call is not None, "edit_message_reply_markup не был вызван"
        assert edit_reply_markup_call.reply_markup == keyboards["podcast_handler"][language].audio_menu_main
