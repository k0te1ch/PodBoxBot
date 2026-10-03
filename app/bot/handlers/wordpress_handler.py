"""Кнопка «Загрузить подкаст на сайт» меню аудио (см. :mod:`handlers.menus`)."""

from loguru import logger
from pydantic import ValidationError
from sagenza_tgbot_sdk.menus import MenuContext

from services.i18n import t
from shared.kafka.models.wordpress_event import WordPressEvent
from utils.menu_context import username as username_of
from utils.publishing import publish_request
from utils.template_store import load as load_template_info

WP_UPLOAD_TOPIC = "publisher.wordpress.upload"


async def upload_WP(ctx: MenuContext) -> None:
    message = ctx.message
    username = username_of(ctx)
    logger.bind(username=username).debug("Начата загрузка в WordPress")

    file_name = message.audio.file_name
    stored = await load_template_info(file_name)
    if stored is None:
        logger.bind(username=username).warning(f"template info not found for {file_name}")
        return await ctx.answer(t("invalid_input", ctx.locale), alert=True)

    info = stored["info"]
    type_episode = stored.get("type_episode")

    audio = message.audio
    info.update(
        {
            "slug": audio.file_name.removesuffix(".mp3"),
            "duration": audio.duration,
        }
    )

    # Отправляем сообщение-статус
    msg = await message.answer("⏳ Отправка поста на сайт...")

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
            # Tags и Chapters в шаблоне необязательны (см. validate_template).
            chapters=info.get("chapters") or [],
            tags=info.get("tags") or [],
            slug=info["slug"],
            duration=info["duration"],
            recording_date=info.get("recording_date"),
            publish_at=info.get("publish_at"),
            type_episode=type_episode,
        )
    except ValidationError as e:
        logger.error(f"Ошибка валидации WordPressEvent: {e.json()}")
        return await ctx.answer("Ошибка валидации данных", alert=True)

    await publish_request(ctx, WP_UPLOAD_TOPIC, "wordpress_event.avsc", event, status=msg, title="Сайт", platform="wp")
