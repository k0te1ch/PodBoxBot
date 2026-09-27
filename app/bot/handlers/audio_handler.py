"""Кнопка «Переслать в чат» меню аудио (см. :mod:`handlers.menus`).

Подтверждение («Точно?» → «Да»/«Нет») рисует меню SDK: у кнопки
``confirm=True``, сюда нажатие доходит только после «Да».
"""

from aiogram import Bot
from loguru import logger
from sagenza_tgbot_sdk.menus import MenuContext

from config import FORWARD_CHAT_USERNAME, FORWARD_PIN_SILENT
from services.i18n import t
from utils.menu_context import username as username_of
from utils.messaging import pin_message
from utils.podcast_methods import generate_podcast_text
from utils.template_store import load as load_template_info


async def forward_to_chat(ctx: MenuContext):
    """Пересылает готовый эпизод в чат и закрепляет его."""
    username = username_of(ctx)
    message = ctx.message
    bot: Bot = ctx.data["bot"]
    logger.debug(f"[{username}]: Forwarding to chat {FORWARD_CHAT_USERNAME}")

    try:
        file_name = message.audio.file_name
        stored = await load_template_info(file_name)
        if stored is None:
            logger.warning(f"[{username}]: template info not found for {file_name}")
            await ctx.answer(t("invalid_input", ctx.locale), alert=True)
            return

        # Генерация текста подкаста
        podcast_text = generate_podcast_text(stored["info"])

        # Пересылка аудио в указанный чат
        forward_message = await bot.send_audio(
            chat_id=FORWARD_CHAT_USERNAME,
            audio=message.audio.file_id,
            caption=podcast_text,
        )

        # Закрепляем аудио в чате
        await pin_message(
            bot,
            username,
            message,
            FORWARD_CHAT_USERNAME,
            forward_message.message_id,
            disable_notification=FORWARD_PIN_SILENT,
        )

        logger.success(f"[{username}]: Successfully forwarded audio")
        await ctx.answer(t("forwarded", ctx.locale))

    except Exception as e:
        logger.error(f"[{username}]: Error in forward_to_chat - {e}")
        await ctx.answer(t("forward_failed", ctx.locale), alert=True)
    finally:
        # После «Да» на месте меню висит вопрос подтверждения — возвращаем меню.
        await ctx.show(ctx.menu_id)
