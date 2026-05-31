import os

from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger
from pydantic import ValidationError

from filters.dispatcher_filters import IsAdmin, IsPrivate
from services import context, keyboards
from shared.kafka.models.boosty_event import BoostyEvent
from shared.kafka.producer import KafkaProducer
from utils.template_store import load as load_template_info

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)

# Kafka config
KAFKA_SERVER = "kafka:9092"
BOOSTY_UPLOAD_TOPIC = "publisher.boosty.upload"
SCHEMA_REGISTRY_URL = "http://schema-registry:8081"
VALUE_SCHEMA_PATH = "/app/shared/kafka/schemas/boosty_event.avsc"


@router.callback_query(F.data == "Boosty_menu")
async def Boosty_menu(callback: CallbackQuery, language: str, username: str) -> None:
    logger.bind(username=username).debug("Открыто меню Boosty")

    await callback.message.edit_reply_markup(reply_markup=keyboards["podcast_handler"][language].Boosty_menu)
    await callback.answer()


@router.callback_query(F.data == "Boosty_upload")
async def upload_Boosty(callback: CallbackQuery, language: str, username: str) -> None:
    logger.bind(username=username).debug("Начата публикация aftershow на Boosty")

    file_name = callback.message.audio.file_name
    stored = await load_template_info(file_name)
    if stored is None:
        logger.bind(username=username).warning(f"template info not found for {file_name}")
        return await callback.answer(context[language].invalid_input, show_alert=True)

    info = stored["info"]

    # Отправляем сообщение-статус
    msg = await callback.message.answer("⏳ Публикация aftershow на Boosty...")

    try:
        # Boosty — только для aftershow: пост уходит на платный уровень
        # (publisher по type_episode="aftershow" выбирает BOOSTY_AFTERSHOW_LEVEL).
        # Кнопка живёт лишь в postshow-меню, type_episode выставляем явно.
        event = BoostyEvent(
            event_type="request",
            username=username,
            status="pending",
            chat_id=str(msg.chat.id),
            message_id=str(msg.message_id),
            number=info["number"],
            title=info["title"],
            comment=info["comment"],
            chapters=info["chapters"],
            tags=info["tags"],
            type_episode="aftershow",
        )

        producer = KafkaProducer(KAFKA_SERVER, SCHEMA_REGISTRY_URL, VALUE_SCHEMA_PATH)
        await producer.send(BOOSTY_UPLOAD_TOPIC, event.model_dump())

        logger.bind(username=username).debug("Boosty upload request sent to Kafka")
        await callback.answer("✅ Запрос на публикацию отправлен. Ожидайте результат", show_alert=True)

    except ValidationError as e:
        logger.error(f"Ошибка валидации BoostyEvent: {e.json()}")
        await callback.answer("Ошибка валидации данных", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при отправке Boosty события: {e}")
        await callback.answer("Ошибка при отправке запроса", show_alert=True)
