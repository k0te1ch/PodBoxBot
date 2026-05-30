"""Tests for the Kafka producer."""

from unittest.mock import MagicMock, patch

import pytest


class TestKafkaProducer:
    @patch("app.shared.kafka.producer.avro")
    @patch("app.shared.kafka.producer.AvroProducer")
    def test_init_only_stores_config(self, mock_avro_producer, mock_avro):
        """Конструктор лишь сохраняет конфиг — без avro.load и без AvroProducer
        (схема/брокер подключаются лениво при первом send)."""
        from app.shared.kafka.producer import KafkaProducer

        producer = KafkaProducer("kafka:9092", "http://registry:8081", "/schemas/test.avsc")

        assert producer.kafka_server == "kafka:9092"
        assert producer.schema_registry_url == "http://registry:8081"
        assert producer.value_schema_path == "/schemas/test.avsc"
        assert producer.producer is None
        mock_avro.load.assert_not_called()
        mock_avro_producer.assert_not_called()

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

        # send triggers the lazy avro.load + AvroProducer construction.
        mock_avro.load.assert_called_once_with("/schemas/test.avsc")
        mock_avro_producer_cls.assert_called_once()
        mock_producer_instance.produce.assert_called_once()
        mock_producer_instance.flush.assert_called_once()
