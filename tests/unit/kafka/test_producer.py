"""Tests for the Kafka producer."""

from unittest.mock import MagicMock, patch

import pytest

SCHEMA = '{"type": "record", "name": "test", "fields": [{"name": "key", "type": "string"}]}'


class TestKafkaProducer:
    @patch("app.shared.kafka.producer.SchemaRegistryClient")
    @patch("app.shared.kafka.producer.Producer")
    def test_init_only_stores_config(self, mock_producer_cls, mock_registry_cls):
        """Конструктор лишь сохраняет конфиг — без чтения схемы, registry и брокера
        (всё это подключается лениво при первом send)."""
        from app.shared.kafka.producer import KafkaProducer

        producer = KafkaProducer("kafka:9092", "http://registry:8081", "/schemas/test.avsc")

        assert producer.kafka_server == "kafka:9092"
        assert producer.schema_registry_url == "http://registry:8081"
        assert producer.value_schema_path == "/schemas/test.avsc"
        assert producer.producer is None
        mock_registry_cls.assert_not_called()
        mock_producer_cls.assert_not_called()

    @patch("app.shared.kafka.producer.wait_for_kafka_stack")
    @patch("app.shared.kafka.producer.AvroSerializer")
    @patch("app.shared.kafka.producer.SchemaRegistryClient")
    @patch("app.shared.kafka.producer.Producer")
    @pytest.mark.asyncio
    async def test_send(self, mock_producer_cls, mock_registry_cls, mock_serializer_cls, mock_wait, tmp_path):
        # Readiness-гейт — инфраструктурная зависимость; мокаем как и брокер.
        async def _noop(*args, **kwargs):
            return None

        mock_wait.side_effect = _noop
        schema_path = tmp_path / "test.avsc"
        schema_path.write_text(SCHEMA, encoding="utf-8")
        mock_serializer_cls.return_value = MagicMock(return_value=b"payload")
        mock_producer_instance = mock_producer_cls.return_value

        from app.shared.kafka.producer import KafkaProducer

        producer = KafkaProducer("kafka:9092", "http://registry:8081", str(schema_path))
        await producer.send("test-topic", {"key": "value"})
        await producer.send("test-topic", {"key": "again"})

        # send лениво поднимает registry, сериализатор и producer — один раз.
        mock_registry_cls.assert_called_once_with({"url": "http://registry:8081"})
        mock_serializer_cls.assert_called_once_with(mock_registry_cls.return_value, SCHEMA)
        mock_producer_cls.assert_called_once_with({"bootstrap.servers": "kafka:9092"})
        mock_producer_instance.produce.assert_called_with(topic="test-topic", value=b"payload")
        assert mock_producer_instance.flush.call_count == 2
