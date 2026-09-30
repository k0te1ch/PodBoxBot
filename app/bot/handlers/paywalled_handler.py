"""Кнопки публикации послешоу на VK Donut, Patreon и Sponsr (см. :mod:`handlers.menus`).

Площадки отличаются только моделью события и топиком, поэтому хендлер один:
:func:`upload_to` собирает его под конкретную площадку. Boosty живёт в своём
модуле — у его события своя история схемы.
"""

from dataclasses import dataclass

from loguru import logger
from pydantic import ValidationError
from sagenza_tgbot_sdk.menus import MenuContext

from config import FILES_PATH
from services.i18n import t
from shared.kafka.models.paywalled_event import PatreonEvent, PaywalledPostEvent, SponsrEvent, VkEvent
from utils.menu_context import username as username_of
from utils.publishing import publish_request
from utils.template_store import load as load_template_info


@dataclass(frozen=True)
class Platform:
    key: str
    title: str
    event_cls: type[PaywalledPostEvent]

    @property
    def topic(self) -> str:
        return f"publisher.{self.key}.upload"

    @property
    def schema(self) -> str:
        return f"{self.key}_event.avsc"


VK = Platform("vk", "VK Donut", VkEvent)
PATREON = Platform("patreon", "Patreon", PatreonEvent)
SPONSR = Platform("sponsr", "Sponsr", SponsrEvent)


def upload_to(platform: Platform):
    async def upload(ctx: MenuContext) -> None:
        message = ctx.message
        username = username_of(ctx)
        log = logger.bind(username=username)
        log.debug(f"Начата публикация aftershow на {platform.title}")

        file_name = message.audio.file_name
        stored = await load_template_info(file_name)
        if stored is None:
            log.warning(f"template info not found for {file_name}")
            return await ctx.answer(t("invalid_input", ctx.locale), alert=True)

        info = stored["info"]
        msg = await message.answer(t("paywalled_publishing", ctx.locale, platform=platform.title))
        try:
            event = platform.event_cls(
                event_type="request",
                username=username,
                status="pending",
                chat_id=str(msg.chat.id),
                message_id=str(msg.message_id),
                path=f"{FILES_PATH}/{file_name}",
                number=info["number"],
                title=info["title"],
                comment=info["comment"],
                chapters=info.get("chapters", []),
                tags=info.get("tags", []),
                type_episode="aftershow",
            )
        except ValidationError as e:
            log.error(f"Ошибка валидации {platform.event_cls.__name__}: {e.json()}")
            return await ctx.answer("Ошибка валидации данных", alert=True)

        await publish_request(ctx, platform.topic, platform.schema, event)

    upload.__name__ = f"upload_{platform.key}"
    return upload
