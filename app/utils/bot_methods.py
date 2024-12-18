import asyncio
import os
import re
import zipfile
from collections.abc import AsyncGenerator, Callable
from pathlib import Path

import aiofiles
import toml
from aiogram import Bot, exceptions
from aiogram.types import Message
from aiogram.types.input_file import DEFAULT_CHUNK_SIZE, InputFile
from config import ADMINS_ID, FILES_PATH, LOCAL, LOGS_PATH, PODCAST_PATH
from loguru import logger
from services import redis

# TODO: Рестарт бота

CHUNK_SIZE = 64 * 1024  # Размер блока 64 КБ


def shutdown_bot():
    exit()


@logger.catch
def get_zip_logs(log_name: str) -> Path | None:
    """
    Creates a ZIP archive of log files from the log directory and returns the path to the archive.
    If an error occurs or there are no logs to archive, it logs the error/warning and returns None.

    Args:
        log_name (str): The name of the ZIP file to create.

    Returns:
        log_zip (Path | None): The path to the created ZIP archive, or None if no logs were found or an error occurred.
    """
    try:
        # Retrieve all log files with the .log extension in the LOGS_PATH directory
        log_files = sorted(LOGS_PATH.glob("*.log"))

        if not log_files:
            logger.warning("No log files found for archiving.")
            return None

        # Define the path for the ZIP archive
        log_zip = FILES_PATH / log_name

        # Create the ZIP archive and write log files into it
        with zipfile.ZipFile(log_zip, mode="w") as archive:
            for log_file in log_files:
                if log_file.is_file():  # Ensure it is a file, not a directory
                    archive.write(log_file, arcname=f"logs/{log_file.name}")

        return log_zip  # Return the path to the created ZIP archive

    except Exception as e:
        # Log the error without interrupting the program
        logger.error(f"Error occurred while creating the log archive: {e}")
        return None


class CustomFSInputFile(InputFile):
    def __init__(
        self,
        path: str | Path,
        filename: str | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        progress_callback: Callable[[int], None] | None = None,
    ):
        """
        Represents object for uploading files from filesystem with progress tracking.

        :param path: Path to file
        :param filename: Filename to be propagated to telegram.
            By default, will be parsed from path
        :param chunk_size: Uploading chunk size
        :param progress_callback: Callable to track progress, receives number of bytes read
        """
        if filename is None:
            filename = os.path.basename(path)
        super().__init__(filename=filename, chunk_size=chunk_size)

        self.path = path
        self.size = Path(path).stat().st_size
        self.progress_callback = progress_callback

    async def read(self, bot: "Bot") -> AsyncGenerator[bytes, None]:
        async with aiofiles.open(self.path, "rb") as f:
            total_read = 0
            prev_percent = -1
            while chunk := await f.read(self.chunk_size):
                total_read += len(chunk)
                if total_read // self.size * 100 != prev_percent:
                    prev_percent = total_read // self.size * 100

                    logger.debug(f"Uploading: {(total_read / self.size) * 100:.2f}%")
                    if self.progress_callback:
                        await self.progress_callback(total_read)

                yield chunk


async def telegram_progress_callback(bytes_uploaded: int, message: Message, total_size: int):
    progress = (bytes_uploaded / total_size) * 100
    await message.edit_text(f"Загрузка файла: {progress:.2f}%")


@logger.catch
async def monitor_file_progress(
    file_path: Path,
    total_size: int,
    progress_callback: Callable[[int, int], None],
    poll_interval: float = 0.5,
) -> True | False:
    """
    Отслеживает прогресс скачивания файла, мониторя файловую систему.

    :param file_path: Путь к файлу, который загружается.
    :param total_size: Общий размер файла в байтах.
    :param progress_callback: Callback для отслеживания прогресса.
    :param poll_interval: Интервал опроса файловой системы (в секундах).
    :return bool: Возвращает True при успехе или False при неудаче
    """
    logger.debug("Monitor task created")

    dots_cycle = iter([".", "..", "...", ""])
    downloaded_size = 0
    mp3_file = None

    if file_path.is_file() and not LOCAL:
        mp3_file = file_path
        logger.debug(f"Используем переданный файл: {mp3_file.name}")

    while downloaded_size < total_size:
        try:
            # Поиск файла, если он ещё не был определён
            if not mp3_file:
                logger.debug(f"Ищем скачивающийся файл{next(dots_cycle)}")
                for file in file_path.iterdir():
                    if file.is_file() and file.stem.isdigit():
                        mp3_file = file
                        logger.debug(f"Найден файл: {mp3_file.name}")
                        break

            # Отслеживание прогресса файла
            if mp3_file and mp3_file.exists():
                downloaded_size = mp3_file.stat().st_size
                logger.debug(f"Текущий размер файла: {downloaded_size} из {total_size}")
                await progress_callback(downloaded_size)
            elif mp3_file and not mp3_file.exists():
                if PODCAST_PATH.exists():
                    mp3_file = PODCAST_PATH
                else:
                    raise FileNotFoundError("Файл исчез")

            await asyncio.sleep(poll_interval)

        except Exception as e:
            logger.error(f"Ошибка при отслеживании файла: {e}")
            break

    # Завершение мониторинга
    if downloaded_size >= total_size:
        logger.info("Файл полностью загружен!")
        return True
    else:
        logger.warning("Мониторинг завершён, но файл не достиг полного размера")
        return False


async def send_message_to_users_handler(
    user_id: int, text: str, disable_notification: bool = False, parse_mode: str = "html"
) -> bool:
    """
    Safe messages sender
    :param bot:
    :param user_id:
    :param text:
    :param disable_notification:
    :return:
    """
    # TODO: Logging
    from bot import bot

    try:
        await bot.send_message(user_id, text, disable_notification=disable_notification, parse_mode=parse_mode)
    except exceptions.TelegramForbiddenError:
        logger.error(f"Target [ID:{user_id}]: бот заблокирован пользователем или доступ запрещен")
    except exceptions.TelegramNotFound:
        logger.error(f"Target [ID:{user_id}]: неверный ID пользователя")
    except exceptions.TelegramRetryAfter as e:
        logger.error(f"Target [ID:{user_id}]: превышен лимит запросов. " f"Ожидание {e.retry_after} секунд.")
        await asyncio.sleep(e.retry_after)
        return await send_message_to_users_handler(bot, user_id, text, disable_notification, parse_mode=parse_mode)
    except exceptions.TelegramBadRequest:
        logger.error(f"Target [ID:{user_id}]: Чат не найден")
    except exceptions.TelegramUnauthorizedError:
        logger.error(f"Target [ID:{user_id}]: пользователь деактивирован")
    except exceptions.TelegramAPIError:
        logger.exception(f"Target [ID:{user_id}]: ошибка API Telegram")
    else:
        logger.info(f"Target [ID:{user_id}]: сообщение успешно отправлено")
        return True
    return False


async def send_message_to_users(
    text: str, users_list: list[int], disable_notification: bool = False, parse_mode: str = "html"
) -> int:
    """
    Simple broadcaster
    :return: Count of messages
    """
    # TODO: Logging
    count = 0
    try:
        for user_id in users_list:
            if await send_message_to_users_handler(user_id, text, disable_notification, parse_mode):
                count += 1
            # 20 messages per second (Limit: 30 messages per second)
            await asyncio.sleep(0.05)
    finally:
        logger.info(f"{count} messages successful sent")

    return count


async def send_release_note() -> None:
    if not await check_version():
        return
    release_note = await get_release_note()

    await send_message_to_users(release_note, ADMINS_ID, True, parse_mode="markdown")


async def get_release_note():
    # Открываем файл с использованием aiofiles
    async with aiofiles.open("CHANGELOG.md", "r") as f:
        content = await f.read()

    # Извлекаем версию и дату из первой строки или другого места
    version_pattern = re.compile(r"# (\d+\.\d+\.\d+)")
    date_pattern = re.compile(r"\((\d{1,2}\.\d{1,2}\.\d{4})\)")  # Ожидаем дату в формате ДД.ММ.ГГГГ

    version_match = version_pattern.search(content)
    date_match = date_pattern.search(content)

    version = version_match.group(1) if version_match else "Неизвестно"
    date = date_match.group(1) if date_match else "Неизвестно"

    # Оформление текста с использованием Markdown
    formatted_notes = f"*Бот обновлён!* \n\n*Список изменений (версия {version}, от {date}):*\n\n"

    # Разбиваем на секции (Добавлено, Улучшено, Исправлено) с поддержкой списков
    sections = ["Добавлено", "Улучшено", "Исправлено"]
    for section in sections:
        section_pattern = re.compile(rf"## {section}(.+?)(?=## |\n#|\Z)", re.DOTALL)
        section_match = section_pattern.search(content)
        if section_match:
            formatted_notes += f"_{section}_:\n"
            items = section_match.group(1).strip().split("\n")
            for item in items:
                formatted_notes += f"• {item.replace('- ', '', 1).strip()}\n"
            formatted_notes += "\n"

    return formatted_notes.strip()


async def check_version() -> True | False:
    bot_version = await redis.get("bot_version")
    current_bot_version = await get_version()

    if not current_bot_version:
        return False

    if current_bot_version != bot_version:
        await redis.set("bot_version", current_bot_version)
        return True
    return False


async def get_version() -> str | None:
    # Открываем файл с использованием aiofiles
    async with aiofiles.open("pyproject.toml", "r") as f:
        content = await f.read()

    # Загружаем данные с помощью toml
    config = toml.loads(content)

    # Извлекаем версию
    version = config.get("tool", {}).get("poetry", {}).get("version", None)

    return version
