from aiogram import Bot
from loguru import logger


def _stage(event: dict) -> str | None:
    """Шаг публикации из ``metadata`` (publisher'ы присылают его не всегда)."""
    metadata = event.get("metadata") or {}
    return metadata.get("stage")


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

        await self._edit(chat_id, message_id, text)

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
            if stage := _stage(event):
                text += f" на шаге `{stage}`"
            if error:
                text += f"\n`{error}`"

        await self._edit(chat_id, message_id, text)

    async def update_upload_retry(self, event: dict):
        """Сообщает, что попытка публикации не удалась и publisher повторяет её."""
        chat_id = event.get("chat_id")
        message_id = event.get("message_id")

        if not chat_id or not message_id:
            logger.warning(f"Missing chat_id or message_id in event: {event}")
            return

        metadata = event.get("metadata") or {}
        attempt = metadata.get("attempt", "?")
        attempts = metadata.get("attempts", "?")
        stage = metadata.get("stage", "?")
        number = event.get("number")
        subject = f"Эпизод *{number}*" if number else f"Файл *{event.get('file_name', '')}*"
        text = f"🔁 {subject}: попытка {attempt}/{attempts} не удалась на шаге `{stage}`, повторяю"
        await self._edit(chat_id, message_id, text)

    async def _edit(self, chat_id, message_id, text: str) -> None:
        try:
            await self.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Ошибка обновления Telegram-сообщения: {e}")
