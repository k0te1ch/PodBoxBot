"""Кнопка «Загрузить подкаст на FTP» меню аудио (см. :mod:`handlers.menus`)."""

from loguru import logger
from pydantic import ValidationError
from sagenza_tgbot_sdk.menus import MenuContext

from config import FILES_PATH
from shared.kafka.models.upload_event import UploadEvent
from utils.menu_context import username as username_of
from utils.publishing import publish_request
from utils.template_store import load as load_template_info

UPLOAD_TOPIC = "publisher.ftp.upload"


async def upload_FTP(ctx: MenuContext):
    """Обработчик загрузки файла на FTP через Kafka"""
    message = ctx.message
    username = username_of(ctx)
    logger.debug(f"[{username}]: Начало загрузки на FTP")

    if not message.audio:
        await ctx.answer("Ошибка: нет файла для загрузки", alert=True)
        return

    file_name = message.audio.file_name
    file_path = f"{FILES_PATH}/{file_name}"

    # Подтягиваем type_episode из sidecar — для будущих платных publisher'ов
    # это сигнал, надо ли вешать paywall. FTP сам paywall не использует,
    # но прокидывает поле дальше через Kafka для совместимости со схемой.
    stored = await load_template_info(file_name)
    type_episode = stored.get("type_episode") if stored else None

    msg = await message.answer("Отправка аудио на FTP")

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
        return await ctx.answer("Ошибка валидации данных", alert=True)

    await publish_request(ctx, UPLOAD_TOPIC, "upload_event.avsc", event)
