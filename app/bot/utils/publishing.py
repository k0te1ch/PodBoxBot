"""Отправка запроса на публикацию в Kafka и ответ админу по итогу.

Общий путь для FTP, WordPress и Boosty: событие уже собрано хендлером,
здесь — продюсер с адресами из конфига, отправка и одинаковые ответы.
"""

from aiogram.types import Message
from loguru import logger
from pydantic import BaseModel
from sagenza_tgbot_sdk.menus import MenuContext

from config import KAFKA_SERVER, SCHEMA_REGISTRY_URL
from services import publish_board
from services.i18n import t
from services.metrics import bot_metrics
from services.publish_board import StatusRef, boards
from shared.kafka.producer import KafkaProducer

SCHEMAS_DIR = "/app/shared/kafka/schemas"
QUEUED_STATUS = "{title}: запрос принят, жду сервис публикации…"
FAILED_ROW = "❌ запрос не отправлен: очередь публикаций недоступна"
FAILED_STATUS = "❌ {title}: запрос не отправлен, очередь публикаций недоступна\n{error}"


def board_title(info: dict | None, file_name: str) -> str:
    """Заголовок табло публикации: по номеру выпуска, а без шаблона по имени файла."""
    number = (info or {}).get("number")
    return f"Выпуск {number}: публикация" if number else f"{file_name}: публикация"


async def _set_board(status: StatusRef, platform: str | None, state: str, text: str, error: str | None = None) -> bool:
    """Состояние площадки в табло публикации; False, если табло для этого сообщения нет."""
    board = boards.get(status.chat_id, status.message_id)
    if board is None or platform is None:
        return False
    await boards.update(board, platform, state, text, error=error)
    return True


async def _set_status(status: Message | StatusRef | None, text: str) -> None:
    """Правит статус-сообщение публикации; его сбой не должен ронять кнопку."""
    if status is None or isinstance(status, StatusRef):
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
    status: Message | StatusRef | None = None,
    title: str = "Публикация",
    platform: str | None = None,
) -> bool:
    """Отправляет ``event`` в ``topic`` и отвечает на нажатие кнопки; True при успехе.

    ``status`` — сообщение-табло, которое дальше правят события publisher'а
    (:mod:`services.publish_board`): здесь в строку площадки пишется, ушёл ли
    запрос в очередь. ``platform`` — метка площадки в
    метриках (``ftp``, ``wp``, ``boosty``, …); без неё запрос не считается.
    """
    try:
        producer = KafkaProducer(KAFKA_SERVER, SCHEMA_REGISTRY_URL, f"{SCHEMAS_DIR}/{schema}")
        await producer.send(topic, event.model_dump())
    except Exception as e:
        logger.error(f"[Kafka] failed to send {type(event).__name__} to {topic}: {e!r}")
        if platform:
            bot_metrics.publish_request_failed(platform)
        reason = f"{type(e).__name__}: {e}"
        if not (
            isinstance(status, StatusRef)
            and await _set_board(status, platform, publish_board.FAILED, FAILED_ROW, error=reason)
        ):
            await _set_status(status, FAILED_STATUS.format(title=title, error=reason))
        await ctx.answer(t("publish_send_failed", ctx.locale), alert=True)
        return False
    logger.info(f"[Kafka] {type(event).__name__} sent to {topic}")
    if platform:
        await bot_metrics.publish_requested(
            platform,
            getattr(event, "type_episode", None),
            number=getattr(event, "number", None),
            file_name=getattr(event, "file_name", None),
        )
    if not (
        isinstance(status, StatusRef)
        and await _set_board(status, platform, publish_board.QUEUED, publish_board.QUEUED_TEXT)
    ):
        await _set_status(status, QUEUED_STATUS.format(title=title))
    # Короткий всплывающий ответ, а не окно: статус и так виден в табло ниже.
    await ctx.answer(t("publish_sent", ctx.locale))
    return True
