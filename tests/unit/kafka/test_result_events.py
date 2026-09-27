"""Статусы result-событий publisher'ов: success, failure, retrying."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.kafka.handlers.upload_event import handle_result_event
from services.telegram_updater import TelegramUpdater

EVENT = {"event_type": "result", "chat_id": "1", "message_id": "2", "number": "42"}
RETRY_META = {"stage": "verify", "attempt": "2", "attempts": "5"}


@pytest.fixture
def updater():
    updater = MagicMock(
        update_upload_result=AsyncMock(), update_upload_retry=AsyncMock(), update_upload_progress=AsyncMock()
    )
    with patch("services.telegram_updater", updater):
        yield updater


@pytest.mark.asyncio
async def test_success_is_reported_only_on_explicit_status(updater):
    await handle_result_event({**EVENT, "status": "success"})
    updater.update_upload_result.assert_awaited_once_with({**EVENT, "status": "success"}, success=True)


@pytest.mark.asyncio
async def test_failure_passes_the_error(updater):
    event = {**EVENT, "status": "failure", "error": "boom", "metadata": RETRY_META}
    await handle_result_event(event)
    updater.update_upload_result.assert_awaited_once_with(event, success=False, error="boom")


@pytest.mark.asyncio
async def test_retrying_is_not_a_success(updater):
    event = {**EVENT, "status": "retrying", "metadata": RETRY_META}
    await handle_result_event(event)
    updater.update_upload_retry.assert_awaited_once_with(event)
    updater.update_upload_result.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "pending", "weird"])
async def test_unknown_status_does_not_claim_success(updater, status):
    await handle_result_event({**EVENT, "status": status})
    updater.update_upload_result.assert_not_awaited()
    updater.update_upload_progress.assert_not_awaited()


def _text(bot) -> str:
    return bot.edit_message_text.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_retry_message_names_attempt_and_stage():
    bot = MagicMock(edit_message_text=AsyncMock())
    await TelegramUpdater(bot).update_upload_retry({**EVENT, "metadata": RETRY_META})
    assert "2/5" in _text(bot)
    assert "verify" in _text(bot)
    assert "42" in _text(bot)


@pytest.mark.asyncio
async def test_retry_message_survives_missing_metadata():
    bot = MagicMock(edit_message_text=AsyncMock())
    await TelegramUpdater(bot).update_upload_retry(dict(EVENT))
    assert "?/?" in _text(bot)


@pytest.mark.asyncio
@pytest.mark.parametrize(("metadata", "has_stage"), [(RETRY_META, True), (None, False)])
async def test_failure_message_names_the_stage_when_known(metadata, has_stage):
    bot = MagicMock(edit_message_text=AsyncMock())
    await TelegramUpdater(bot).update_upload_result({**EVENT, "metadata": metadata}, success=False, error="boom")
    assert ("на шаге `verify`" in _text(bot)) is has_stage
    assert "boom" in _text(bot)
