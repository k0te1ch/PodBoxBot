from aiogram import Bot
from loguru import logger


class TelegramUpdater:
    """Сервис для обновления сообщений в Telegram."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def update_upload_progress(self, event: dict, finished: bool = False):
        chat_id = event["chat_id"]
        message_id = event["message_id"]
        file_name = event["file_name"]
        progress = event.get("progress", 0)

        text = (
            f"📤 Загрузка *{file_name}*\nПрогресс: {progress:.1f}%"
            if not finished
            else f"✅ Файл *{file_name}* успешно загружен!"
        )

        try:
            await self.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Ошибка обновления Telegram-сообщения: {e}")
