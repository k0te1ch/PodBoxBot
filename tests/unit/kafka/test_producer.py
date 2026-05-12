"""Tests for the Kafka producer."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestKafkaProducer:
    @patch("app.shared.kafka.producer.avro")
    @patch("app.shared.kafka.producer.AvroProducer")
    def test_init(self, mock_avro_producer, mock_avro):
        mock_avro.load.return_value = {"type": "record", "name": "test"}

        from app.shared.kafka.producer import KafkaProducer

        producer = KafkaProducer("kafka:9092", "http://registry:8081", "/schemas/test.avsc")

        assert producer.kafka_server == "kafka:9092"
        assert producer.schema_registry_url == "http://registry:8081"
        mock_avro.load.assert_called_once_with("/schemas/test.avsc")
        mock_avro_producer.assert_called_once()

    @patch("app.shared.kafka.producer.avro")
    @patch("app.shared.kafka.producer.AvroProducer")
    @pytest.mark.asyncio
    async def test_send(self, mock_avro_producer_cls, mock_avro):
        mock_avro.load.return_value = {"type": "record", "name": "test"}
        mock_producer_instance = mock_avro_producer_cls.return_value
        mock_producer_instance.produce = MagicMock()
        mock_producer_instance.flush = MagicMock()

        from app.shared.kafka.producer import KafkaProducer

        producer = KafkaProducer("kafka:9092", "http://registry:8081", "/schemas/test.avsc")
        await producer.send("test-topic", {"key": "value"})

        mock_producer_instance.produce.assert_called_once()
        mock_producer_instance.flush.assert_called_once()
