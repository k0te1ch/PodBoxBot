"""Отправка запроса на публикацию в Kafka и ответ админу по итогу.

Общий путь для FTP, WordPress и Boosty: событие уже собрано хендлером,
здесь — продюсер с адресами из конфига, отправка и одинаковые ответы.
"""

from loguru import logger
from pydantic import BaseModel
from sagenza_tgbot_sdk.menus import MenuContext

from config import KAFKA_SERVER, SCHEMA_REGISTRY_URL
from shared.kafka.producer import KafkaProducer

SCHEMAS_DIR = "/app/shared/kafka/schemas"
SENT_TEXT = "✅ Запрос на публикацию отправлен. Ожидайте результат"
FAILED_TEXT = "Ошибка при отправке запроса"


async def publish_request(ctx: MenuContext, topic: str, schema: str, event: BaseModel) -> bool:
    """Отправляет ``event`` в ``topic`` и отвечает на нажатие кнопки; True при успехе."""
    try:
        producer = KafkaProducer(KAFKA_SERVER, SCHEMA_REGISTRY_URL, f"{SCHEMAS_DIR}/{schema}")
        await producer.send(topic, event.model_dump())
    except Exception as e:
        logger.error(f"[Kafka] failed to send {type(event).__name__} to {topic}: {e!r}")
        await ctx.answer(FAILED_TEXT, alert=True)
        return False
    logger.info(f"[Kafka] {type(event).__name__} sent to {topic}")
    await ctx.answer(SENT_TEXT, alert=True)
    return True
