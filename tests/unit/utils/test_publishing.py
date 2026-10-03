from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from services.i18n import t
from utils import publishing


class _Event(BaseModel):
    number: int = 1


@pytest.mark.asyncio
async def test_sends_with_configured_addresses_and_confirms():
    ctx = MagicMock(answer=AsyncMock(), locale="ru")
    producer = MagicMock(send=AsyncMock())
    with patch.object(publishing, "KafkaProducer", return_value=producer) as cls:
        assert await publishing.publish_request(ctx, "topic", "x.avsc", _Event()) is True

    cls.assert_called_once_with(
        publishing.KAFKA_SERVER, publishing.SCHEMA_REGISTRY_URL, "/app/shared/kafka/schemas/x.avsc"
    )
    producer.send.assert_awaited_once_with("topic", {"number": 1})
    # Всплывающая подсказка, а не окно, которое надо закрывать.
    ctx.answer.assert_awaited_once_with(t("publish_sent"))


@pytest.mark.asyncio
async def test_reports_failure_instead_of_success():
    ctx = MagicMock(answer=AsyncMock(), locale="ru")
    producer = MagicMock(send=AsyncMock(side_effect=RuntimeError("kafka down")))
    with patch.object(publishing, "KafkaProducer", return_value=producer):
        assert await publishing.publish_request(ctx, "topic", "x.avsc", _Event()) is False

    ctx.answer.assert_awaited_once_with(t("publish_send_failed"), alert=True)


@pytest.mark.asyncio
async def test_status_message_says_the_request_is_queued():
    ctx = MagicMock(answer=AsyncMock(), locale="ru")
    status = MagicMock(edit_text=AsyncMock())
    producer = MagicMock(send=AsyncMock())
    with patch.object(publishing, "KafkaProducer", return_value=producer):
        await publishing.publish_request(ctx, "topic", "x.avsc", _Event(), status=status, title="FTP")

    assert "FTP: запрос принят" in status.edit_text.call_args.args[0]


@pytest.mark.asyncio
async def test_status_message_names_the_send_error():
    ctx = MagicMock(answer=AsyncMock(), locale="ru")
    status = MagicMock(edit_text=AsyncMock())
    producer = MagicMock(send=AsyncMock(side_effect=RuntimeError("kafka down")))
    with patch.object(publishing, "KafkaProducer", return_value=producer):
        await publishing.publish_request(ctx, "topic", "x.avsc", _Event(), status=status, title="Boosty")

    text = status.edit_text.call_args.args[0]
    assert text.startswith("❌ Boosty")
    assert "kafka down" in text
