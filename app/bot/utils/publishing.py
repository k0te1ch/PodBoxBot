"""Отправка запроса на публикацию в Kafka и ответ админу по итогу.

Общий путь для FTP, WordPress и Boosty: событие уже собрано хендлером,
здесь — продюсер с адресами из конфига, отправка и одинаковые ответы.
"""

from aiogram.types import Message
from loguru import logger
from pydantic import BaseModel
from sagenza_tgbot_sdk.menus import MenuContext

from config import KAFKA_SERVER, SCHEMA_REGISTRY_URL
from services.metrics import bot_metrics
from shared.kafka.producer import KafkaProducer

SCHEMAS_DIR = "/app/shared/kafka/schemas"
SENT_TEXT = "✅ Запрос на публикацию отправлен. Ожидайте результат"
FAILED_TEXT = "Ошибка при отправке запроса"
QUEUED_STATUS = "{title}: запрос принят, ждём сервис публикации…"
FAILED_STATUS = "❌ {title}: запрос не отправлен — очередь публикаций недоступна.\n{error}"


async def _set_status(status: Message | None, text: str) -> None:
    """Правит статус-сообщение публикации; его сбой не должен ронять кнопку."""
    if status is None:
        return
    try:
        await status.edit_text(text, parse_mode=None)
    except Exception as e:
        logger.warning(f"status message not updated: {e!r}")


async def publish_request(
    ctx: MenuContext,
    topic: str,
    schema: str,
    event: BaseModel,
    status: Message | None = None,
    title: str = "Публикация",
    platform: str | None = None,
) -> bool:
    """Отправляет ``event`` в ``topic`` и отвечает на нажатие кнопки; True при успехе.

    ``status`` — сообщение, которое дальше правят события publisher'а: здесь в
    него пишется, ушёл ли запрос в очередь. ``platform`` — метка площадки в
    метриках (``ftp``, ``wp``, ``boosty``, …); без неё запрос не считается.
    """
    try:
        producer = KafkaProducer(KAFKA_SERVER, SCHEMA_REGISTRY_URL, f"{SCHEMAS_DIR}/{schema}")
        await producer.send(topic, event.model_dump())
    except Exception as e:
        logger.error(f"[Kafka] failed to send {type(event).__name__} to {topic}: {e!r}")
        if platform:
            bot_metrics.publish_request_failed(platform)
        await _set_status(status, FAILED_STATUS.format(title=title, error=f"{type(e).__name__}: {e}"))
        await ctx.answer(FAILED_TEXT, alert=True)
        return False
    logger.info(f"[Kafka] {type(event).__name__} sent to {topic}")
    if platform:
        await bot_metrics.publish_requested(
            platform,
            getattr(event, "type_episode", None),
            number=getattr(event, "number", None),
            file_name=getattr(event, "file_name", None),
        )
    await _set_status(status, QUEUED_STATUS.format(title=title))
    await ctx.answer(SENT_TEXT, alert=True)
    return True
