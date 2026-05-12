import os

from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger
from pydantic import ValidationError
from shared.kafka.models.wordpress_event import WordPressEvent
from shared.kafka.producer import KafkaProducer

from filters.dispatcher_filters import IsAdmin, IsPrivate
from services import context, keyboards
from utils.validators import validate_template

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)

# Kafka config
KAFKA_SERVER = "kafka:9092"
WP_UPLOAD_TOPIC = "publisher.wordpress.upload"
SCHEMA_REGISTRY_URL = "http://schema-registry:8081"
VALUE_SCHEMA_PATH = "/app/shared/kafka/schemas/wordpress_event.avsc"


@router.callback_query(F.data == "WPMenu")
async def WP_menu(callback: CallbackQuery, language: str, username: str) -> None:
    logger.bind(username=username).debug("Открыто меню WordPress")

    await callback.message.edit_reply_markup(
        reply_markup=keyboards["podcast_handler"][language].WPMenu
    )
    await callback.answer()


@router.callback_query(F.data == "WP_upload")
async def upload_WP(callback: CallbackQuery, language: str, username: str) -> None:
    logger.bind(username=username).debug("Начата загрузка в WordPress")

    message = callback.message.reply_to_message
    if not message or not message.text:
        return await callback.answer(context[language].invalid_input, show_alert=True)

    info = validate_template(message.text)
    if not info:
        logger.bind(username=username).debug("Ошибка валидации шаблона")
        return await callback.answer(context[language].invalid_input, show_alert=True)

    audio = callback.message.audio
    info.update(
        {
            "slug": audio.file_name.removesuffix(".mp3"),
            "duration": audio.duration,
        }
    )

    # Отправляем сообщение-статус
    msg = await callback.message.answer("⏳ Отправка поста на сайт...")

    try:
        event = WordPressEvent(
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
            slug=info["slug"],
            duration=info["duration"],
        )

        producer = KafkaProducer(KAFKA_SERVER, SCHEMA_REGISTRY_URL, VALUE_SCHEMA_PATH)
        await producer.send(WP_UPLOAD_TOPIC, event.model_dump())

        logger.bind(username=username).debug("WordPress upload request sent to Kafka")
        await callback.answer("✅ Запрос на публикацию отправлен. Ожидайте результат", show_alert=True)

    except ValidationError as e:
        logger.error(f"Ошибка валидации WordPressEvent: {e.json()}")
        await callback.answer("Ошибка валидации данных", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при отправке WordPress события: {e}")
        await callback.answer("Ошибка при отправке запроса", show_alert=True)
