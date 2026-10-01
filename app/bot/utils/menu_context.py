"""Мелочи для хендлеров кнопок меню SDK (:class:`~sagenza_tgbot_sdk.menus.MenuContext`)."""

from collections.abc import Callable

from sagenza_tgbot_sdk.menus import MenuContext

from filters.dispatcher_filters import IsAdmin


def username(ctx: MenuContext) -> str:
    """Username нажавшего — для логов, как в остальных хендлерах."""
    user = ctx.event.from_user if ctx.event is not None else None
    return (user.username if user else None) or "unknown"


def is_admin(ctx: MenuContext) -> bool:
    """``visible_if`` меню: тот же список ADMINS, что у фильтра IsAdmin."""
    return ctx.event is not None and IsAdmin(ctx.event)


def only_inside(menu_id: str) -> Callable[[MenuContext], bool]:
    """``visible_if`` для ссылки на меню, у которого нет своей кнопки.

    Список записей открывает хендлер (``ctx.show``), кнопка в родителе ему не
    нужна. Но спрятать ссылку насовсем нельзя: SDK пускает нажатие в меню,
    только когда видимы все ссылки на пути к нему, и кнопки самого списка
    (запись, страницы, «Назад» из карточки) отвечали бы «Кнопка недоступна».
    Поэтому ссылка видима ровно для нажатий внутри этого меню. Когда рисуется
    родитель, ``ctx.menu_id`` другой, и кнопки в нём нет.
    """
    return lambda ctx: ctx.menu_id == menu_id
