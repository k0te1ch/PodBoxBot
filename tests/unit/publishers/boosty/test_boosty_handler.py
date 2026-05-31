"""Tests for the Boosty publisher Kafka handler (main.py) и модели события."""

from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.shared.kafka.models.boosty_event import BoostyEvent


@pytest.fixture
def mock_producer():
    producer = AsyncMock()
    producer.send = AsyncMock()
    return producer


@pytest.fixture
def patched_publisher(monkeypatch):
    """Подменяет _publisher.client на AsyncMock (instance создаётся при импорте).

    get_container_id → 1900545, upload_audio → ("aud-1", 123), upload_image →
    "img-1", publish → "post-1", ensure_auth → no-op. Конфиг уровня/цены задаём,
    чтобы happy-path не падал на «not configured».
    """
    from app.publishers.Boosty import main

    client = AsyncMock()
    client.ensure_auth = AsyncMock(return_value=None)
    client.get_container_id = AsyncMock(return_value=1900545)
    client.upload_audio = AsyncMock(return_value=("aud-1", 123))
    client.upload_image = AsyncMock(return_value="img-1")
    client.publish = AsyncMock(return_value="post-1")
    monkeypatch.setattr(main._publisher, "client", client)
    monkeypatch.setattr(main, "BOOSTY_SUBSCRIPTION_LEVEL_ID", "407063")
    monkeypatch.setattr(main, "BOOSTY_PRICE", 10)
    monkeypatch.setattr(main, "BOOSTY_COVER_PATH", "/app/files/boosty_pscover.png")
    monkeypatch.setattr(main, "BOOSTY_ADVERTISER_INFO", "")
    return main, client


class TestHandleUpload:
    @pytest.mark.asyncio
    async def test_successful_publish(self, sample_boosty_event_dict, mock_producer, patched_publisher):
        main, client = patched_publisher
        await main.handle_upload(sample_boosty_event_dict, mock_producer)

        client.upload_audio.assert_awaited_once()
        # mp3-путь и container_id пробрасываются в upload_audio
        assert client.upload_audio.await_args.args[0] == "/app/files/0123_postshow.mp3"
        assert client.upload_audio.await_args.args[1] == 1900545
        client.upload_image.assert_awaited_once_with("/app/files/boosty_pscover.png")
        client.publish.assert_awaited_once()

        mock_producer.send.assert_called_once()
        result = mock_producer.send.call_args[0][1]
        assert result["event_type"] == "result"
        assert result["status"] == "success"
        assert result["post_id"] == "post-1"

    @pytest.mark.asyncio
    async def test_publish_uses_fixed_level_and_price(
        self, sample_boosty_event_dict, mock_producer, patched_publisher
    ):
        main, client = patched_publisher
        await main.handle_upload(sample_boosty_event_dict, mock_producer)

        kwargs = client.publish.await_args.kwargs
        assert kwargs["subscription_level_id"] == "407063"
        assert kwargs["price"] == 10
        assert kwargs["cover_id"] == "img-1"
        assert kwargs["audio_id"] == "aud-1"

    @pytest.mark.asyncio
    async def test_missing_path_emits_failure(self, sample_boosty_event_dict, mock_producer, patched_publisher):
        main, client = patched_publisher
        sample_boosty_event_dict.pop("path", None)

        await main.handle_upload(sample_boosty_event_dict, mock_producer)

        client.upload_audio.assert_not_awaited()
        result = mock_producer.send.call_args[0][1]
        assert result["status"] == "failure"
        assert "path" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_failure_emits_failure_event(self, sample_boosty_event_dict, mock_producer, patched_publisher):
        main, client = patched_publisher
        client.publish.side_effect = RuntimeError("boom")

        await main.handle_upload(sample_boosty_event_dict, mock_producer)

        result = mock_producer.send.call_args[0][1]
        assert result["status"] == "failure"
        assert "boom" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_payload_skipped(self, mock_producer, patched_publisher):
        main, _ = patched_publisher
        await main.handle_upload({"invalid": "data"}, mock_producer)
        mock_producer.send.assert_not_called()


class TestBoostyEventModel:
    def test_valid_event(self, sample_boosty_event_dict):
        event = BoostyEvent(**sample_boosty_event_dict)
        assert event.number == "123"
        assert event.event_type == "request"
        assert event.path == "/app/files/0123_postshow.mp3"
        assert event.chapters == [["00:00:00", "Начало"], ["00:10:00", "Середина"]]

    def test_invalid_status(self, sample_boosty_event_dict):
        sample_boosty_event_dict["status"] = "invalid_status"
        with pytest.raises(ValidationError):
            BoostyEvent(**sample_boosty_event_dict)

    def test_optional_fields_default_none(self, sample_boosty_event_dict):
        sample_boosty_event_dict.pop("path", None)
        sample_boosty_event_dict.pop("type_episode", None)
        event = BoostyEvent(**sample_boosty_event_dict)
        assert event.path is None
        assert event.paywall_tier is None
        assert event.post_id is None

    def test_model_dump_roundtrip(self, sample_boosty_event_dict):
        event = BoostyEvent(**sample_boosty_event_dict)
        dump = event.model_dump()
        assert dump["tags"] == ["тест", "подкаст"]
        assert BoostyEvent(**dump) == event
