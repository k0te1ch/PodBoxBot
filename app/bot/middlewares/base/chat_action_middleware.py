from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from loguru import logger


class ChatActionMiddleware(BaseMiddleware):
    """Middleware для отображения индикатора действий (например, 'typing') во время выполнения длительных операций"""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        """Основная логика middleware: показывает индикатор действия при длительных операциях

        Args:
            handler (Callable): Целевая функция-обработчик события
            event (Message): Объект сообщения
            data (Dict[str, Any]): Словарь с контекстными данными

        Returns:
            Any: Результат выполнения обработчика
        """
        # Получаем тип длительной операции
        action_type = get_flag(data, "long_operation")

        if not action_type:
            logger.debug(f"Длительная операция не найдена для чата {event.chat.id}")
            return await handler(event, data)

        # Логируем начало длительной операции
        logger.info(
            f"Запущена длительная операция '{action_type}' в чате {event.chat.id}"
        )

        # Отображаем индикатор действия
        async with ChatActionSender(action=action_type, chat_id=event.chat.id):
            result = await handler(event, data)

        # Логируем завершение длительной операции
        logger.info(
            f"Длительная операция '{action_type}' завершена в чате {event.chat.id}"
        )

        return result
