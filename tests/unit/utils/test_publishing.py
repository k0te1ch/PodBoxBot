from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from utils import publishing


class _Event(BaseModel):
    number: int = 1


@pytest.mark.asyncio
async def test_sends_with_configured_addresses_and_confirms():
    ctx = MagicMock(answer=AsyncMock())
    producer = MagicMock(send=AsyncMock())
    with patch.object(publishing, "KafkaProducer", return_value=producer) as cls:
        assert await publishing.publish_request(ctx, "topic", "x.avsc", _Event()) is True

    cls.assert_called_once_with(
        publishing.KAFKA_SERVER, publishing.SCHEMA_REGISTRY_URL, "/app/shared/kafka/schemas/x.avsc"
    )
    producer.send.assert_awaited_once_with("topic", {"number": 1})
    ctx.answer.assert_awaited_once_with(publishing.SENT_TEXT, alert=True)


@pytest.mark.asyncio
async def test_reports_failure_instead_of_success():
    ctx = MagicMock(answer=AsyncMock())
    producer = MagicMock(send=AsyncMock(side_effect=RuntimeError("kafka down")))
    with patch.object(publishing, "KafkaProducer", return_value=producer):
        assert await publishing.publish_request(ctx, "topic", "x.avsc", _Event()) is False

    ctx.answer.assert_awaited_once_with(publishing.FAILED_TEXT, alert=True)
