import os

from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger
from pydantic import ValidationError

from filters.dispatcher_filters import IsAdmin, IsPrivate
from services import context, keyboards
from shared.kafka.models.wordpress_event import WordPressEvent
from utils.publishing import publish_request
from utils.template_store import load as load_template_info

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)

WP_UPLOAD_TOPIC = "publisher.wordpress.upload"


@router.callback_query(F.data == "WP_menu")
async def WP_menu(callback: CallbackQuery, language: str, username: str) -> None:
    logger.bind(username=username).debug("Открыто меню WordPress")

    await callback.message.edit_reply_markup(reply_markup=keyboards["podcast_handler"][language].WP_menu)
    await callback.answer()


@router.callback_query(F.data == "WP_upload")
async def upload_WP(callback: CallbackQuery, language: str, username: str) -> None:
    logger.bind(username=username).debug("Начата загрузка в WordPress")

    file_name = callback.message.audio.file_name
    stored = await load_template_info(file_name)
    if stored is None:
        logger.bind(username=username).warning(f"template info not found for {file_name}")
        return await callback.answer(context[language].invalid_input, show_alert=True)

    info = stored["info"]
    type_episode = stored.get("type_episode")

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
            recording_date=info.get("recording_date"),
            type_episode=type_episode,
        )
    except ValidationError as e:
        logger.error(f"Ошибка валидации WordPressEvent: {e.json()}")
        return await callback.answer("Ошибка валидации данных", show_alert=True)

    await publish_request(callback, WP_UPLOAD_TOPIC, "wordpress_event.avsc", event)
