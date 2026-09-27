import inspect
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import InlineKeyboardMarkup

from handlers import admin_handler
from keyboards import admin_panel_kb, bot_commands_kb


def _callback_data(markup: InlineKeyboardMarkup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row}


def _handled_callbacks() -> set[str]:
    source = inspect.getsource(admin_handler)
    return set(re.findall(r'F\.data == "([^"]+)"', source))


@pytest.mark.parametrize("markup", [admin_panel_kb(), bot_commands_kb()])
def test_every_admin_button_has_a_handler(markup):
    assert _callback_data(markup) <= _handled_callbacks()


@pytest.mark.asyncio
async def test_admin_command_sends_the_panel():
    msg = MagicMock()
    msg.answer = AsyncMock()

    await admin_handler.admin(msg, username="admin")

    assert isinstance(msg.answer.call_args.kwargs["reply_markup"], InlineKeyboardMarkup)


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [admin_handler.bot_panel, admin_handler.back, admin_handler.tests_panel])
async def test_panel_callbacks_edit_with_markup(handler):
    callback = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await handler(callback, username="admin")

    assert isinstance(callback.message.edit_text.call_args.kwargs["reply_markup"], InlineKeyboardMarkup)
