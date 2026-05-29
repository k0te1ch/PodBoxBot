"""Tests for the TelegramUpdater service."""

from unittest.mock import AsyncMock

import pytest
from app.bot.services.telegram_updater import TelegramUpdater


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.edit_message_text = AsyncMock()
    return bot


@pytest.fixture
def updater(mock_bot):
    return TelegramUpdater(mock_bot)


class TestUpdateUploadProgress:
    @pytest.mark.asyncio
    async def test_progress_message(self, updater, mock_bot):
        event = {
            "chat_id": "123",
            "message_id": "456",
            "file_name": "test.mp3",
            "progress": 50.0,
        }
        await updater.update_upload_progress(event)

        mock_bot.edit_message_text.assert_called_once()
        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert "test.mp3" in call_kwargs["text"]
        assert "50.0%" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_finished_message(self, updater, mock_bot):
        event = {
            "chat_id": "123",
            "message_id": "456",
            "file_name": "test.mp3",
            "progress": 1.0,
        }
        await updater.update_upload_progress(event, finished=True)

        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert "успешно загружен" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_progress_fraction_converted(self, updater, mock_bot):
        event = {
            "chat_id": "123",
            "message_id": "456",
            "file_name": "test.mp3",
            "progress": 0.75,
        }
        await updater.update_upload_progress(event)

        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert "75.0%" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_missing_chat_id_skips(self, updater, mock_bot):
        event = {"message_id": "456", "file_name": "test.mp3", "progress": 0.5}
        await updater.update_upload_progress(event)
        mock_bot.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_message_id_skips(self, updater, mock_bot):
        event = {"chat_id": "123", "file_name": "test.mp3", "progress": 0.5}
        await updater.update_upload_progress(event)
        mock_bot.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_message_error_handled(self, updater, mock_bot):
        mock_bot.edit_message_text.side_effect = Exception("Telegram API error")
        event = {
            "chat_id": "123",
            "message_id": "456",
            "file_name": "test.mp3",
            "progress": 0.5,
        }
        # Should not raise
        await updater.update_upload_progress(event)


class TestUpdateUploadResult:
    @pytest.mark.asyncio
    async def test_success_with_episode_number(self, updater, mock_bot):
        event = {
            "chat_id": "123",
            "message_id": "456",
            "number": "100",
        }
        await updater.update_upload_result(event, success=True)

        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert "100" in call_kwargs["text"]
        assert "черновики" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_success_with_file_name(self, updater, mock_bot):
        event = {
            "chat_id": "123",
            "message_id": "456",
            "file_name": "rz-100.mp3",
        }
        await updater.update_upload_result(event, success=True)

        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert "rz-100.mp3" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_failure_with_error(self, updater, mock_bot):
        event = {
            "chat_id": "123",
            "message_id": "456",
            "number": "100",
        }
        await updater.update_upload_result(event, success=False, error="Session expired")

        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert "Ошибка" in call_kwargs["text"]
        assert "Session expired" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_failure_without_error(self, updater, mock_bot):
        event = {
            "chat_id": "123",
            "message_id": "456",
            "file_name": "test.mp3",
        }
        await updater.update_upload_result(event, success=False)

        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert "Ошибка" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_missing_ids_skips(self, updater, mock_bot):
        event = {"number": "100"}
        await updater.update_upload_result(event, success=True)
        mock_bot.edit_message_text.assert_not_called()
