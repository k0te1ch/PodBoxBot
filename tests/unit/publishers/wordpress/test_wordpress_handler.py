"""Tests for the WordPress publisher Kafka handler (main.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.shared.kafka.models.wordpress_event import WordPressEvent
from pydantic import ValidationError


class TestHandleUpload:
    @pytest.fixture
    def mock_producer(self):
        producer = AsyncMock()
        producer.send = AsyncMock()
        return producer

    @pytest.mark.asyncio
    async def test_successful_upload(self, sample_wp_event_dict, mock_producer):
        with patch("app.publishers.WordPress.main.WordPress") as MockWP:
            wp_instance = MagicMock()
            wp_instance.upload_post.return_value = True
            wp_instance.last_post_id = None
            wp_instance.__enter__ = MagicMock(return_value=wp_instance)
            wp_instance.__exit__ = MagicMock(return_value=False)
            MockWP.return_value = wp_instance

            from app.publishers.WordPress.main import handle_upload

            await handle_upload(sample_wp_event_dict, mock_producer)

            assert [c.args[1]["event_type"] for c in mock_producer.send.call_args_list].count("result") == 1
            call_args = mock_producer.send.call_args
            result = call_args[0][1]
            assert result["event_type"] == "result"
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_failed_upload(self, sample_wp_event_dict, mock_producer):
        with patch("app.publishers.WordPress.main.WordPress") as MockWP:
            wp_instance = MagicMock()
            wp_instance.upload_post.return_value = False
            wp_instance.__enter__ = MagicMock(return_value=wp_instance)
            wp_instance.__exit__ = MagicMock(return_value=False)
            MockWP.return_value = wp_instance

            from app.publishers.WordPress.main import handle_upload

            await handle_upload(sample_wp_event_dict, mock_producer)

            call_args = mock_producer.send.call_args
            result = call_args[0][1]
            assert result["status"] == "failure"

    @pytest.mark.asyncio
    async def test_exception_during_upload(self, sample_wp_event_dict, mock_producer):
        with patch("app.publishers.WordPress.main.WordPress") as MockWP:
            MockWP.side_effect = RuntimeError("Connection refused")

            from app.publishers.WordPress.main import handle_upload

            await handle_upload(sample_wp_event_dict, mock_producer)

            call_args = mock_producer.send.call_args
            result = call_args[0][1]
            assert result["status"] == "failure"
            assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_failure_is_retried_and_reported(self, sample_wp_event_dict, mock_producer):
        with patch("app.publishers.WordPress.main.WordPress") as MockWP:
            MockWP.side_effect = [RuntimeError("502"), RuntimeError("502"), RuntimeError("502")]

            from app.publishers.WordPress.main import _publisher, handle_upload

            await handle_upload(sample_wp_event_dict, mock_producer)

            attempts = _publisher.retry_attempts
            sent = [c.args[1] for c in mock_producer.send.call_args_list if c.args[1]["event_type"] == "result"]
            assert [e["status"] for e in sent] == ["retrying"] * (attempts - 1) + ["failure"]
            assert sent[0]["metadata"]["stage"] == "publish"
            assert sent[-1]["metadata"]["attempts"] == str(attempts)

    @pytest.mark.asyncio
    async def test_saved_draft_is_verified(
        self, sample_wp_event_dict, mock_producer, verify_published_mock, monkeypatch
    ):
        monkeypatch.setattr("app.publishers.WordPress.main.WP_URL", "https://example.org/")
        with patch("app.publishers.WordPress.main.WordPress") as MockWP:
            wp_instance = MagicMock()
            wp_instance.upload_post.return_value = True
            wp_instance.last_post_id = "777"
            wp_instance.podcast_rest_path.return_value = "/wp/v2/episodes/777"
            wp_instance.__enter__ = MagicMock(return_value=wp_instance)
            wp_instance.__exit__ = MagicMock(return_value=False)
            MockWP.return_value = wp_instance

            from app.publishers.WordPress.main import handle_upload

            await handle_upload(sample_wp_event_dict, mock_producer)

            verify_published_mock.assert_awaited_once()
            url = verify_published_mock.await_args.args[0]
            assert url.endswith("/wp-json/wp/v2/episodes/777?context=edit")
            result = mock_producer.send.call_args.args[1]
            assert result["status"] == "success"
            assert result["metadata"] == {"post_id": "777", "url": url}

    @pytest.mark.asyncio
    async def test_unverified_draft_reports_failure(
        self, sample_wp_event_dict, mock_producer, verify_published_mock, monkeypatch
    ):
        monkeypatch.setattr("app.publishers.WordPress.main.WP_URL", "https://example.org/")
        from sagenza_tgbot_sdk.resilience import NotPublishedError

        verify_published_mock.side_effect = NotPublishedError("u", "HTTP 404")
        with patch("app.publishers.WordPress.main.WordPress") as MockWP:
            wp_instance = MagicMock()
            wp_instance.upload_post.return_value = True
            wp_instance.last_post_id = "777"
            wp_instance.__enter__ = MagicMock(return_value=wp_instance)
            wp_instance.__exit__ = MagicMock(return_value=False)
            MockWP.return_value = wp_instance

            from app.publishers.WordPress.main import _publisher, handle_upload

            await handle_upload(sample_wp_event_dict, mock_producer)

            assert verify_published_mock.await_count == _publisher.verify_attempts
            assert wp_instance.upload_post.call_count == 1
            result = mock_producer.send.call_args.args[1]
            assert result["status"] == "failure"
            assert result["metadata"]["stage"] == "verify"

    @pytest.mark.asyncio
    async def test_invalid_payload_skipped(self, mock_producer):
        from app.publishers.WordPress.main import handle_upload

        await handle_upload({"invalid": "data"}, mock_producer)
        mock_producer.send.assert_not_called()


class TestWordPressEventModel:
    def test_valid_event(self, sample_wp_event_dict):
        event = WordPressEvent(**sample_wp_event_dict)
        assert event.number == "123"
        assert event.event_type == "request"
        assert event.chapters == [["00:00:00", "Начало"], ["00:10:00", "Середина"]]

    def test_invalid_status(self, sample_wp_event_dict):
        sample_wp_event_dict["status"] = "invalid_status"
        with pytest.raises(ValidationError):
            WordPressEvent(**sample_wp_event_dict)

    def test_valid_statuses(self, sample_wp_event_dict):
        for status in ["pending", "success", "failure", None]:
            sample_wp_event_dict["status"] = status
            event = WordPressEvent(**sample_wp_event_dict)
            assert event.status == status

    def test_model_dump(self, sample_wp_event_dict):
        event = WordPressEvent(**sample_wp_event_dict)
        dump = event.model_dump()
        assert isinstance(dump, dict)
        assert dump["number"] == "123"
        assert dump["tags"] == ["тест", "подкаст"]
