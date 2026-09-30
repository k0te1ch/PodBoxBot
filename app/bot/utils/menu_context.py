"""Мелочи для хендлеров кнопок меню SDK (:class:`~sagenza_tgbot_sdk.menus.MenuContext`)."""

from sagenza_tgbot_sdk.menus import MenuContext

from filters.dispatcher_filters import IsAdmin


def username(ctx: MenuContext) -> str:
    """Username нажавшего — для логов, как в остальных хендлерах."""
    user = ctx.event.from_user if ctx.event is not None else None
    return (user.username if user else None) or "unknown"


def is_admin(ctx: MenuContext) -> bool:
    """``visible_if`` меню: тот же список ADMINS, что у фильтра IsAdmin."""
    return ctx.event is not None and IsAdmin(ctx.event)
