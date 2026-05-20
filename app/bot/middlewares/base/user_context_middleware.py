from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from loguru import logger

from config import LANGUAGES

EventType = TypeVar("EventType", bound=TelegramObject)


class UserContextMiddleware(BaseMiddleware):
    """
    Универсальный middleware для добавления в handler данных о языке и имени пользователя.
    Поддерживает Message и CallbackQuery.
    """

    async def get_user(self, event: Message | CallbackQuery) -> User:
        """Извлекает объект пользователя из события"""
        if isinstance(event, (Message, CallbackQuery)):
            return event.from_user
        raise ValueError(f"Неизвестный тип события: {type(event)}")

    async def get_language(self, user: User) -> str:
        """Определяет язык пользователя из Telegram или возвращает 'ru'"""
        language = user.language_code if user.language_code in LANGUAGES else "ru"
        logger.trace(f"Определён язык: {language} для пользователя: {user.id}")
        return language

    async def __call__(
        self,
        handler: Callable[[EventType, dict[str, Any]], Awaitable[Any]],
        event: EventType,
        data: dict[str, Any],
    ) -> Any:
        handler_info = data.get("handler")
        handler_params = getattr(handler_info, "params", {}) if handler_info else {}

        try:
            user = await self.get_user(event)
        except Exception as e:
            logger.warning(f"Не удалось извлечь пользователя: {e}")
            return await handler(event, data)

        if "language" in handler_params:
            data["language"] = await self.get_language(user)

        if "username" in handler_params:
            data["username"] = user.username or "unknown"

        callback_name = getattr(getattr(handler_info, "callback", None), "__name__", "unknown")
        logger.debug(f"[{user.username or 'unknown'}]: Called {callback_name} callback")

        return await handler(event, data)
