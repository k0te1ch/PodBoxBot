"""Глобальный обработчик ошибок: ловит любое необработанное исключение через
`dp.errors` и шлёт разработчику в Telegram.

Раньше уведомление висело на per-observer мидлваре (только `message` и
`callback_query`) — ошибки из остальных обсерверов до DEVELOPER не доходили.
`dp.errors` покрывает всю пропагацию событий. Дополнительно трейсбек
обрезается под лимит Telegram (4096 символов), иначе длинное сообщение
падало с `TelegramBadRequest` и уведомление терялось целиком.
"""

from __future__ import annotations

import traceback
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent
from loguru import logger

from config import DEVELOPER

# Запас под HTML-обвязку сообщения; сам Telegram-лимит — 4096 символов.
_MAX_TB_CHARS = 3500


def _extract_user(event: ErrorEvent) -> str:
    """Достаёт инициатора апдейта (@username или id), N/A если не определить."""
    update = event.update
    for attr in ("message", "edited_message", "callback_query", "my_chat_member", "chat_member"):
        obj = getattr(update, attr, None)
        user = getattr(obj, "from_user", None) if obj is not None else None
        if user is not None:
            return f"@{user.username}" if user.username else str(user.id)
    return "N/A"


async def _notify_developer(bot: Bot, event: ErrorEvent) -> None:
    exc = event.exception
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    if len(tb) > _MAX_TB_CHARS:
        # Хвост важнее головы — там само исключение и ближайшие кадры.
        tb = "…(обрезано)…\n" + tb[-_MAX_TB_CHARS:]

    message = (
        f"⚠️ <b>Ошибка в боте</b>\n\n"
        f"<b>🕒 Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>🆔 Пользователь:</b> {_extract_user(event)}\n"
        f"<b>💥 Ошибка:</b>\n<pre><code>{tb}</code></pre>"
    )
    try:
        await bot.send_message(DEVELOPER, message, parse_mode="HTML")
        logger.info("📬 Сообщение об ошибке отправлено разработчику")
    except Exception as e:
        # Не маскируем исходную ошибку — лишь логируем сбой доставки.
        logger.error(f"❌ Не удалось отправить ошибку разработчику: {e!r}")


def register_error_handler(dp: Dispatcher) -> None:
    """Вешает глобальный `dp.errors`-хендлер, уведомляющий DEVELOPER."""

    @dp.errors()
    async def _on_error(event: ErrorEvent, bot: Bot) -> bool:
        logger.opt(exception=event.exception).error(
            f"🛑 Необработанная ошибка при обработке апдейта: {event.exception!r}"
        )
        if DEVELOPER is not None:
            await _notify_developer(bot, event)
        else:
            logger.warning("DEVELOPER не задан — уведомление об ошибке не отправлено")
        # Помечаем ошибку обработанной: мы её залогировали и уведомили.
        return True
