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

    resolve_level_id → "777", create_post → "post-1", ensure_auth → no-op.
    """
    from app.publishers.Boosty import main

    client = AsyncMock()
    client.ensure_auth = AsyncMock(return_value=None)
    client.resolve_level_id = AsyncMock(return_value="777")
    client.create_post = AsyncMock(return_value="post-1")
    monkeypatch.setattr(main._publisher, "client", client)
    # Дефолтные уровни, чтобы happy-path не падал на «level not configured».
    monkeypatch.setattr(main, "BOOSTY_FREE_LEVEL", "Бесплатный")
    monkeypatch.setattr(main, "BOOSTY_AFTERSHOW_LEVEL", "Подписка")
    return main, client


class TestHandleUpload:
    @pytest.mark.asyncio
    async def test_successful_publish(self, sample_boosty_event_dict, mock_producer, patched_publisher):
        main, client = patched_publisher
        await main.handle_upload(sample_boosty_event_dict, mock_producer)

        client.create_post.assert_awaited_once()
        mock_producer.send.assert_called_once()
        result = mock_producer.send.call_args[0][1]
        assert result["event_type"] == "result"
        assert result["status"] == "success"
        assert result["post_id"] == "post-1"

    @pytest.mark.asyncio
    async def test_main_episode_uses_free_level(
        self, sample_boosty_event_dict, mock_producer, patched_publisher, monkeypatch
    ):
        main, client = patched_publisher
        monkeypatch.setattr(main, "BOOSTY_FREE_LEVEL", "Бесплатный")
        sample_boosty_event_dict["type_episode"] = "main"

        await main.handle_upload(sample_boosty_event_dict, mock_producer)

        client.resolve_level_id.assert_awaited_once_with("Бесплатный")

    @pytest.mark.asyncio
    async def test_aftershow_uses_paid_level(
        self, sample_boosty_event_dict, mock_producer, patched_publisher, monkeypatch
    ):
        main, client = patched_publisher
        monkeypatch.setattr(main, "BOOSTY_AFTERSHOW_LEVEL", "Подписка")
        sample_boosty_event_dict["type_episode"] = "aftershow"

        await main.handle_upload(sample_boosty_event_dict, mock_producer)

        client.resolve_level_id.assert_awaited_once_with("Подписка")

    @pytest.mark.asyncio
    async def test_explicit_paywall_tier_wins(self, sample_boosty_event_dict, mock_producer, patched_publisher):
        main, client = patched_publisher
        sample_boosty_event_dict["type_episode"] = "main"
        sample_boosty_event_dict["paywall_tier"] = "VIP"

        await main.handle_upload(sample_boosty_event_dict, mock_producer)

        client.resolve_level_id.assert_awaited_once_with("VIP")

    @pytest.mark.asyncio
    async def test_failure_emits_failure_event(self, sample_boosty_event_dict, mock_producer, patched_publisher):
        main, client = patched_publisher
        client.create_post.side_effect = RuntimeError("boom")

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
        assert event.chapters == [["00:00:00", "Начало"], ["00:10:00", "Середина"]]

    def test_invalid_status(self, sample_boosty_event_dict):
        sample_boosty_event_dict["status"] = "invalid_status"
        with pytest.raises(ValidationError):
            BoostyEvent(**sample_boosty_event_dict)

    def test_paywall_fields_default_none(self, sample_boosty_event_dict):
        sample_boosty_event_dict.pop("type_episode", None)
        event = BoostyEvent(**sample_boosty_event_dict)
        assert event.paywall_tier is None
        assert event.type_episode is None
        assert event.post_id is None

    def test_model_dump_roundtrip(self, sample_boosty_event_dict):
        event = BoostyEvent(**sample_boosty_event_dict)
        dump = event.model_dump()
        assert dump["tags"] == ["тест", "подкаст"]
        assert BoostyEvent(**dump) == event
