import traceback
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Update
from loguru import logger

from config import DEVELOPER


class ErrorMiddleware(BaseMiddleware):
    """Middleware для перехвата ошибок и уведомления разработчика через Telegram"""

    async def on_error(self, update: Update, exception: Exception, data: dict[str, Any]):
        """Обработка ошибок и уведомление разработчика

        Args:
            update (Update): Объект обновления, вызвавший ошибку
            exception (Exception): Исключение, которое было вызвано
        """
        # Логируем ошибку
        logger.error(
            f"🛑 Ошибка при обработке апдейта:\n"
            f"📦 Update: {update}\n"
            f"💥 Exception: {exception}\n"
            f"🔍 Traceback:\n{traceback.format_exc()}"
        )

        # Формируем сообщение для отправки админу
        error_message = (
            f"⚠️ <b>Ошибка в боте</b>\n\n"
            f"<b>🕒 Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"<b>🆔 Пользователь:</b> {update.from_user.username if update.from_user else 'N/A'}\n"
            f"<b>💥 Ошибка:</b>\n<pre><code>{traceback.format_exc()}</code></pre>"
        )

        # Отправляем сообщение админу
        try:
            await data["bot"].send_message(DEVELOPER, error_message, parse_mode="HTML")
            logger.info("📬 Сообщение об ошибке успешно отправлено админу.")
        except TelegramBadRequest as e:
            logger.error(f"❌ Ошибка при отправке сообщения админу: {e}")

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        """Вызов middleware с обработкой ошибок

        Args:
            handler (Callable): Целевая функция-обработчик события
            event (Update): Текущий апдейт
            data (Dict[str, Any]): Дополнительные данные

        Returns:
            Any: Результат выполнения хендлера
        """
        try:
            logger.debug(f"🔄 Обработка апдейта: {event}")
            return await handler(event, data)
        except Exception as e:
            logger.warning(f"⚠️ Перехвачена ошибка при обработке апдейта: {e}")
            await self.on_error(event, e, data)
            raise e
