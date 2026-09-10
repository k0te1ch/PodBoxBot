from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from handlers.bot_handler import delete_pinned_service_message

BOT_ID = 4242


def _service_message(pinned_by_id: int | None) -> SimpleNamespace:
    """Служебка «... закрепил сообщение»: from_user — тот, кто закрепил."""
    return SimpleNamespace(
        chat=SimpleNamespace(id=-100500),
        message_id=17,
        from_user=None if pinned_by_id is None else SimpleNamespace(id=pinned_by_id),
    )


@pytest.fixture
def bot() -> AsyncMock:
    return AsyncMock(id=BOT_ID)


@pytest.mark.asyncio
async def test_deletes_own_pin_notice(bot):
    message = _service_message(BOT_ID)

    await delete_pinned_service_message(message, bot)

    bot.delete_message.assert_awaited_once_with(chat_id=message.chat.id, message_id=message.message_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("pinned_by_id", [BOT_ID + 1, None], ids=["another user", "no from_user"])
async def test_keeps_pin_notices_the_bot_did_not_make(bot, pinned_by_id):
    await delete_pinned_service_message(_service_message(pinned_by_id), bot)

    bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_failure_is_logged_not_raised(bot, caplog):
    bot.delete_message.side_effect = RuntimeError("message can't be deleted")

    await delete_pinned_service_message(_service_message(BOT_ID), bot)

    assert "message can't be deleted" in caplog.text
