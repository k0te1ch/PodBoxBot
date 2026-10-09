"""Кнопка «Загрузить подкаст на FTP» меню аудио (см. :mod:`handlers.menus`)."""

from loguru import logger
from pydantic import ValidationError
from sagenza_tgbot_sdk.menus import MenuContext

from config import FILES_PATH
from services.i18n import t
from services.publish_board import boards
from shared.kafka.models.upload_event import UploadEvent
from utils.menu_context import username as username_of
from utils.publishing import board_title, publish_request
from utils.template_store import load as load_template_info

UPLOAD_TOPIC = "publisher.ftp.upload"


async def upload_FTP(ctx: MenuContext):
    """Обработчик загрузки файла на FTP через Kafka"""
    message = ctx.message
    username = username_of(ctx)
    logger.debug(f"[{username}]: Начало загрузки на FTP")

    if not message.audio:
        await ctx.answer("Под этим сообщением нет файла", alert=True)
        return

    file_name = message.audio.file_name
    file_path = f"{FILES_PATH}/{file_name}"

    # Без sidecar это файл прошлого выпуска: его mp3 на диске уже заменён,
    # публишеру отправлять нечего. Остальные кнопки публикации отвечают так же.
    stored = await load_template_info(file_name)
    if stored is None:
        logger.warning(f"[{username}]: template info not found for {file_name}")
        return await ctx.answer(t("episode_file_gone", ctx.locale), alert=True)

    # type_episode из sidecar: по нему публишер кладёт послешоу в свою папку.
    type_episode = stored.get("type_episode")

    # Одно табло на все площадки этого файла (services.publish_board).
    msg = await boards.open(message, "ftp", board_title(stored["info"], file_name))

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
            chat_id=str(msg.chat_id),
            type_episode=type_episode,
        )
    except ValidationError as e:
        logger.error(f"UploadEvent validation failed: {e.json()}")
        return await ctx.answer("В описании выпуска не хватает данных для этой площадки", alert=True)

    await publish_request(ctx, UPLOAD_TOPIC, "upload_event.avsc", event, status=msg, title="FTP", platform="ftp")
