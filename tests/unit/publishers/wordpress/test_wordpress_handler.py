"""Tests for the WordPress publisher Kafka handler (main.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.shared.kafka.models.wordpress_event import WordPressEvent
from pydantic import ValidationError


@pytest.mark.skip(
    reason="Publisher service test: WordPress main.py builds a KafkaProducer at import "
    "(avro.load on the in-container path /app/shared/...), unavailable outside the "
    "service container. Re-enable after deferring Kafka/schema init. Follow-up tracked."
)
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
            wp_instance.__enter__ = MagicMock(return_value=wp_instance)
            wp_instance.__exit__ = MagicMock(return_value=False)
            MockWP.return_value = wp_instance

            from app.publishers.WordPress.main import handle_upload

            await handle_upload(sample_wp_event_dict, mock_producer)

            mock_producer.send.assert_called_once()
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
