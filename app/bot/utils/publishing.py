"""Отправка запроса на публикацию в Kafka и ответ админу по итогу.

Общий путь для FTP, WordPress и Boosty: событие уже собрано хендлером,
здесь — продюсер с адресами из конфига, отправка и одинаковые ответы.
"""

from aiogram.types import CallbackQuery
from loguru import logger
from pydantic import BaseModel

from config import KAFKA_SERVER, SCHEMA_REGISTRY_URL
from shared.kafka.producer import KafkaProducer

SCHEMAS_DIR = "/app/shared/kafka/schemas"
SENT_TEXT = "✅ Запрос на публикацию отправлен. Ожидайте результат"
FAILED_TEXT = "Ошибка при отправке запроса"


async def publish_request(callback: CallbackQuery, topic: str, schema: str, event: BaseModel) -> bool:
    """Отправляет ``event`` в ``topic`` и отвечает на callback; True при успехе."""
    try:
        producer = KafkaProducer(KAFKA_SERVER, SCHEMA_REGISTRY_URL, f"{SCHEMAS_DIR}/{schema}")
        await producer.send(topic, event.model_dump())
    except Exception as e:
        logger.error(f"[Kafka] failed to send {type(event).__name__} to {topic}: {e!r}")
        await callback.answer(FAILED_TEXT, show_alert=True)
        return False
    logger.info(f"[Kafka] {type(event).__name__} sent to {topic}")
    await callback.answer(SENT_TEXT, show_alert=True)
    return True
