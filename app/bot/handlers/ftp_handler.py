import os

from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger
from pydantic import ValidationError

from config import FILES_PATH
from filters.dispatcher_filters import IsAdmin, IsPrivate
from services import keyboards
from shared.kafka.models.upload_event import UploadEvent
from utils.publishing import publish_request
from utils.template_store import load as load_template_info

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)


@router.callback_query(F.data == "FTP_menu")
async def FTP_menu(callback: CallbackQuery, language: str, username: str):
    """Обработчик меню FTP"""
    logger.debug(f"[{username}]: Opened FTP_menu")

    await callback.message.edit_reply_markup(reply_markup=keyboards["podcast_handler"][language].FTP_menu)
    await callback.answer()


UPLOAD_TOPIC = "publisher.ftp.upload"


@router.callback_query(F.data == "FTP_upload")
async def upload_FTP(callback: CallbackQuery, username: str):
    """Обработчик загрузки файла на FTP через Kafka"""
    logger.debug(f"[{username}]: Начало загрузки на FTP")

    if not callback.message.audio:
        await callback.answer("Ошибка: нет файла для загрузки", show_alert=True)
        return

    file_name = callback.message.audio.file_name
    file_path = f"{FILES_PATH}/{file_name}"

    # Подтягиваем type_episode из sidecar — для будущих платных publisher'ов
    # это сигнал, надо ли вешать paywall. FTP сам paywall не использует,
    # но прокидывает поле дальше через Kafka для совместимости со схемой.
    stored = await load_template_info(file_name)
    type_episode = stored.get("type_episode") if stored else None

    msg = await callback.message.answer("Отправка аудио на FTP")

    try:
        event = UploadEvent(
            event_type="request",
            file_name=file_name,
            path=file_path,
            username=username,
            metadata=None,
            bytes_uploaded=0,
            total_bytes=0,
            progress=0.0,
            transfer_speed=0.0,
            status="pending",
            message_id=str(msg.message_id),
            chat_id=str(msg.chat.id),
            type_episode=type_episode,
        )
    except ValidationError as e:
        logger.error(f"UploadEvent validation failed: {e.json()}")
        return await callback.answer("Ошибка валидации данных", show_alert=True)

    await publish_request(callback, UPLOAD_TOPIC, "upload_event.avsc", event)
