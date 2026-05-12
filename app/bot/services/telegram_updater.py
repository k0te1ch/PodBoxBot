from aiogram import Bot
from loguru import logger


class TelegramUpdater:
    """Сервис для обновления сообщений в Telegram."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def update_upload_progress(self, event: dict, finished: bool = False):
        """Обновляет сообщение с прогрессом загрузки (FTP)."""
        chat_id = event.get("chat_id")
        message_id = event.get("message_id")
        file_name = event.get("file_name", "")
        progress = event.get("progress", 0)

        if not chat_id or not message_id:
            logger.warning(f"Missing chat_id or message_id in event: {event}")
            return

        if finished:
            text = f"✅ Файл *{file_name}* успешно загружен!"
        else:
            pct = progress * 100 if isinstance(progress, float) and progress <= 1 else progress
            text = f"📤 Загрузка *{file_name}*\nПрогресс: {pct:.1f}%"

        try:
            await self.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Ошибка обновления Telegram-сообщения: {e}")

    async def update_upload_result(self, event: dict, success: bool, error: str | None = None):
        """Обновляет сообщение с результатом загрузки (FTP/WordPress)."""
        chat_id = event.get("chat_id")
        message_id = event.get("message_id")
        file_name = event.get("file_name", "")
        number = event.get("number", "")

        if not chat_id or not message_id:
            logger.warning(f"Missing chat_id or message_id in event: {event}")
            return

        if success:
            if number:
                text = f"✅ Пост для эпизода *{number}* успешно сохранён в черновики!"
            else:
                text = f"✅ Файл *{file_name}* успешно загружен!"
        else:
            if number:
                text = f"❌ Ошибка публикации эпизода *{number}*"
            else:
                text = f"❌ Ошибка загрузки файла *{file_name}*"
            if error:
                text += f"\n`{error}`"

        try:
            await self.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Ошибка обновления Telegram-сообщения: {e}")
