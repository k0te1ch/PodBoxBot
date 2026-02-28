from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, User
from loguru import logger

from config import LANGUAGES


class GeneralMiddleware(BaseMiddleware):
    """
    Middleware для добавления языка и имени пользователя в data при обработке сообщений
    """

    async def get_language(self, user: User) -> str:
        """
        Определяет язык пользователя

        Args:
            user: объект пользователя из Telegram

        Returns:
            str: Код языка из LANGUAGES или "ru" по умолчанию
        """

        language = user.language_code if user.language_code in LANGUAGES else "ru"
        logger.trace(f"Определён язык: {language} для пользователя: {user.id}")
        return language

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        """Основная логика middleware: Добавляет язык и имя пользователя

        Args:
            handler (Callable[[Message, Dict[str, Any]], Awaitable[Any]]): Целевая функция-обработчик
            event (Message): событие сообщения
            data (Dict[str, Any]): словарь с данными для передачи в handler

        Returns:
            Any: Результат выполнения handler
        """

        handler_info = data.get("handler")

        # Безопасно извлекаем параметры, если handler определён
        handler_params = getattr(handler_info, "params", {}) if handler_info else {}

        user = event.from_user

        if "language" in handler_params:
            data["language"] = await self.get_language(user)

        if "username" in handler_params:
            data["username"] = user.username or "unknown"

        callback_name = getattr(getattr(handler_info, "callback", None), "__name__", "unknown")
        logger.opt(colors=True).debug(
            f"<y>[{event.from_user.username or "unknown"}]</y>: Called {callback_name} callback"
        )

        # Выполняем целевой обработчик
        return await handler(event, data)
