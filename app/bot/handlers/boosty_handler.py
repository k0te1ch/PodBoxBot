"""Кнопка «Опубликовать aftershow на Boosty» меню аудио (см. :mod:`handlers.menus`)."""

from loguru import logger
from pydantic import ValidationError
from sagenza_tgbot_sdk.menus import MenuContext

from config import FILES_PATH
from services.i18n import t
from shared.kafka.models.boosty_event import BoostyEvent
from utils.menu_context import username as username_of
from utils.publishing import publish_request
from utils.template_store import load as load_template_info

BOOSTY_UPLOAD_TOPIC = "publisher.boosty.upload"


async def upload_Boosty(ctx: MenuContext) -> None:
    message = ctx.message
    username = username_of(ctx)
    logger.bind(username=username).debug("Начата публикация aftershow на Boosty")

    file_name = message.audio.file_name
    stored = await load_template_info(file_name)
    if stored is None:
        logger.bind(username=username).warning(f"template info not found for {file_name}")
        return await ctx.answer(t("invalid_input", ctx.locale), alert=True)

    info = stored["info"]
    file_path = f"{FILES_PATH}/{file_name}"

    # Отправляем сообщение-статус
    msg = await message.answer("⏳ Публикация aftershow на Boosty...")

    try:
        # Boosty — только для aftershow: пост уходит на платный уровень + цену
        # (publisher берёт BOOSTY_SUBSCRIPTION_LEVEL_ID/BOOSTY_PRICE из конфига).
        # Кнопка живёт лишь в postshow-меню, type_episode выставляем явно.
        event = BoostyEvent(
            event_type="request",
            username=username,
            status="pending",
            chat_id=str(msg.chat.id),
            message_id=str(msg.message_id),
            path=file_path,
            number=info["number"],
            title=info["title"],
            comment=info["comment"],
            # postshow-эпизоды могут не иметь таймлайна/тегов в sidecar
            chapters=info.get("chapters", []),
            tags=info.get("tags", []),
            publish_at=info.get("publish_at"),
            type_episode="aftershow",
        )
    except ValidationError as e:
        logger.error(f"Ошибка валидации BoostyEvent: {e.json()}")
        return await ctx.answer("Ошибка валидации данных", alert=True)

    await publish_request(
        ctx, BOOSTY_UPLOAD_TOPIC, "boosty_event.avsc", event, status=msg, title="Boosty", platform="boosty"
    )
