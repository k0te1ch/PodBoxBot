"""Tests for the TelegramUpdater service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from app.bot.services.telegram_updater import TelegramUpdater

IDS = {"chat_id": "123", "message_id": "456"}


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
    @pytest.mark.parametrize(
        ("metadata", "expected"),
        [
            (
                {"platform": "wp", "action": "draft"},
                "✅ Эпизод <b>100</b>: пост сохранён в черновики на сайте, подписчики его пока не видят",
            ),
            ({"platform": "boosty", "action": "published"}, "✅ Эпизод <b>100</b> опубликован на Boosty"),
            ({"platform": "vk", "action": "published"}, "✅ Эпизод <b>100</b> опубликован в VK Donut"),
            ({"platform": "patreon", "action": "published"}, "✅ Эпизод <b>100</b> опубликован на Patreon"),
            (
                {"platform": "boosty", "action": "scheduled", "publish_at": "01.10.2027 12:00"},
                "✅ Эпизод <b>100</b>: отложенная публикация на Boosty запланирована на 01.10.2027 12:00",
            ),
        ],
        ids=["wp-draft", "boosty", "vk", "patreon", "boosty-scheduled"],
    )
    async def test_success_text_matches_what_the_platform_did(self, updater, mock_bot, metadata, expected):
        event = {**IDS, "number": "100", "metadata": metadata}

        await updater.update_upload_result(event, success=True)

        assert mock_bot.edit_message_text.call_args.kwargs["text"] == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("platform", ["boosty", "vk", "patreon"])
    async def test_published_platforms_are_not_called_drafts(self, updater, mock_bot, platform):
        # Раньше любой успех с номером эпизода назывался «сохранён в черновики»,
        # хотя Boosty, VK и Patreon публикуют пост сразу.
        event = {**IDS, "number": "100", "metadata": {"platform": platform, "action": "published"}}

        await updater.update_upload_result(event, success=True)

        assert "черновик" not in mock_bot.edit_message_text.call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_success_without_action_promises_nothing(self, updater, mock_bot):
        event = {**IDS, "number": "100"}

        await updater.update_upload_result(event, success=True)

        assert mock_bot.edit_message_text.call_args.kwargs["text"] == "✅ Эпизод <b>100</b>: публикация завершена"

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


def _text(bot) -> str:
    return bot.edit_message_text.call_args.kwargs["text"]


class TestStatusMessage:
    @pytest.mark.asyncio
    async def test_stage_start_is_shown(self, updater, mock_bot):
        event = {**IDS, "number": "42", "status": "pending", "metadata": {"stage": "upload_audio"}}
        await updater.update_upload_progress(event)
        assert "загрузка аудио" in _text(mock_bot)
        assert "42" in _text(mock_bot)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("type_episode", "kind"), [("main", "основной эпизод"), ("aftershow", "послешоу")])
    async def test_both_episodes_get_progress_and_final_status(self, updater, mock_bot, type_episode, kind):
        event = {**IDS, "file_name": "0042_rz_27092026.mp3", "type_episode": type_episode}
        await updater.update_upload_progress({**event, "status": "uploading", "progress": 0.42})
        assert "42.0%" in _text(mock_bot)
        assert kind in _text(mock_bot)

        await updater.update_upload_result({**event, "status": "success"}, success=True)
        assert "успешно загружен" in _text(mock_bot)
        assert kind in _text(mock_bot)

    @pytest.mark.asyncio
    async def test_late_progress_does_not_overwrite_the_result(self, updater, mock_bot):
        event = {**IDS, "file_name": "a.mp3"}
        await updater.update_upload_result(event, success=True)
        await updater.update_upload_progress({**event, "status": "uploading", "progress": 0.99})
        mock_bot.edit_message_text.assert_awaited_once()
        assert "успешно" in _text(mock_bot)

    @pytest.mark.asyncio
    async def test_file_names_and_errors_are_escaped_html(self, updater, mock_bot):
        event = {**IDS, "file_name": "0042_rz_<x>.mp3", "metadata": {"stage": "upload"}}
        await updater.update_upload_result(event, success=False, error="bad `thing` & <tag>")
        text = _text(mock_bot)
        assert "0042_rz_&lt;x&gt;.mp3" in text
        assert "bad `thing` &amp; &lt;tag&gt;" in text
        assert mock_bot.edit_message_text.call_args.kwargs["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    async def test_final_status_waits_out_flood_limit(self, updater, mock_bot):
        flood = TelegramRetryAfter(method=MagicMock(), message="Too Many Requests", retry_after=1)
        mock_bot.edit_message_text.side_effect = [flood, None]
        with patch("asyncio.sleep", new=AsyncMock()) as sleep:
            await updater.update_upload_result({**IDS, "file_name": "a.mp3"}, success=True)
        sleep.assert_awaited_once_with(1)
        assert mock_bot.edit_message_text.await_count == 2

    @pytest.mark.asyncio
    async def test_not_modified_is_quiet(self, updater, mock_bot):
        mock_bot.edit_message_text.side_effect = TelegramBadRequest(
            method=MagicMock(), message="Bad Request: message is not modified"
        )
        await updater.update_upload_progress({**IDS, "file_name": "a.mp3", "progress": 0.5})

    @pytest.mark.asyncio
    async def test_success_shows_post_url(self, updater, mock_bot):
        event = {**IDS, "number": "42", "metadata": {"url": "https://example.com/p/1"}}
        await updater.update_upload_result(event, success=True)
        assert "https://example.com/p/1" in _text(mock_bot)
