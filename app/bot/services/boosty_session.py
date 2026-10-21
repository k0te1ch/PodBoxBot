"""Сообщение админам, когда у публишера Boosty слетел вход.

Публишер шлёт событие ``session`` только при смене состояния, но после его
перезапуска первое состояние приходит снова. Флаг в Redis помнит, что админы
уже знают о поломке: одно сообщение на поломку и одно на восстановление.
"""

from aiogram import Bot
from loguru import logger

from services.i18n import t
from utils.safe_text import safe_text

DOWN_KEY = "boosty:session:down"


async def on_session_event(event: dict, bot: Bot, redis, admin_ids: list[int], locale: str) -> None:
    status = event.get("status")
    if status == "failure":
        if not await redis.set(DOWN_KEY, "1", nx=True):
            return
        text = t("boosty_session_down", locale, error=safe_text(event.get("error") or "-"))
    elif status == "success":
        if not await redis.delete(DOWN_KEY):
            return
        text = t("boosty_session_restored", locale)
    else:
        logger.warning(f"Boosty session event with unknown status {status!r} ignored")
        return
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.warning(f"boosty session: could not notify admin {admin_id}: {e!r}")
