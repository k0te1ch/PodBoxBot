"""Отмечает в метриках, что админ пользуется ботом.

В метрики уходит только число активных админов за окно и время последнего
действия (см. :mod:`services.metrics`); id пользователя наружу не выходит.
"""

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.metrics import bot_metrics


class AdminActivityMiddleware(BaseMiddleware):
    def __init__(self, admin_ids: Iterable[int]) -> None:
        self.admin_ids = frozenset(admin_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is not None and user.id in self.admin_ids:
            bot_metrics.admin_seen(user.id)
        return await handler(event, data)
