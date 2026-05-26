import asyncio
import os
import re
import signal
import zipfile
from pathlib import Path

import aiofiles
import toml
from aiogram import Bot, exceptions
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from loguru import logger

from config import ADMINS_ID, FILES_PATH, LOGS_PATH
from services import redis
from services.none_module import _NoneModule

# TODO: Рестарт бота

CHUNK_SIZE = 64 * 1024  # Размер блока 64 КБ


# region Bot methods
def shutdown_bot():
    os.kill(os.getpid(), signal.SIGINT)


def restart_bot():
    exit()


# region Logs methods
@logger.catch
def get_zip_logs(log_name: str) -> Path | None:
    """
    Creates a ZIP archive of log files from the log directory and returns the path to the archive
    If an error occurs or there are no logs to archive, it logs the error/warning and returns None

    Args:
        log_name (str): The name of the ZIP file to create

    Returns:
        log_zip (Path | None): The path to the created ZIP archive, or None if no logs were found or an error occurred
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


# region Release notes


async def send_release_note() -> None:
    if not await check_version():
        return
    release_note = await get_release_note()

    await broadcast_message_to_users(release_note, ADMINS_ID, True, parse_mode=ParseMode.MARKDOWN_V2)


async def get_release_note():
    # Открываем файл с использованием aiofiles
    async with aiofiles.open("CHANGELOG.md") as f:
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


async def check_version() -> bool:
    """True if pyproject.toml version differs from what's stored in redis.

    Without redis we have no place to persist the last-seen version, so
    every restart would look like a fresh release — skip silently instead.
    """
    if isinstance(redis, _NoneModule):
        logger.debug("Redis is not configured; skipping version check")
        return False

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
    async with aiofiles.open("pyproject.toml") as f:
        content = await f.read()

    # Загружаем данные с помощью toml
    config = toml.loads(content)

    # Извлекаем версию
    version = config.get("tool", {}).get("poetry", {}).get("version", None)

    return version


# region Messages methods
@logger.catch
async def send_message_to_user(
    user_id: int,
    text: str | list[str],
    disable_notification: bool = False,
    parse_mode: str = ParseMode.HTML,
    disable_web_page_preview: bool = False,
    max_length: int = 4096,
    delay: float = 0.05,
) -> bool:
    """
    Safe message sender with support for splitting long messages and adding delays

    :param user_id: Telegram user ID
    :param text: The message text or messages
    :param disable_notification: If True, sends the message silently
    :param parse_mode: Message parse mode (e.g., "html")
    :param disable_web_page_preview: If True, disables link previews
    :param max_length: Maximum allowed length of a single message
    :param delay: Delay in seconds between sending messages
    :return: True if at least one message was successfully sent, False otherwise
    """
    from main import bot

    if isinstance(text, str):
        messages = split_into_messages("", "", [text], max_length)
    else:
        messages = text

    sent_any = False

    for message in messages:
        try:
            await bot.send_message(
                user_id,
                message,
                disable_notification=disable_notification,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
            logger.info(f"Target [ID:{user_id}]: сообщение успешно отправлено")
            sent_any = True
        except exceptions.TelegramForbiddenError:
            logger.error(f"Target [ID:{user_id}]: бот заблокирован пользователем или доступ запрещён")
            break
        except exceptions.TelegramNotFound:
            logger.error(f"Target [ID:{user_id}]: неверный ID пользователя")
            break
        except exceptions.TelegramRetryAfter as e:
            logger.error(f"Target [ID:{user_id}]: превышен лимит запросов. Ожидание {e.retry_after} секунд")
            await asyncio.sleep(e.retry_after)
            return await send_message_to_user(
                user_id,
                text,
                disable_notification,
                parse_mode,
                disable_web_page_preview,
                max_length,
                delay,
            )
        except exceptions.TelegramBadRequest as e:
            logger.error(f"Target [ID:{user_id}]: некорректный запрос. Ошибка: {e}")
            logger.error(f"Сообщение: {message}")
        except exceptions.TelegramUnauthorizedError:
            logger.error(f"Target [ID:{user_id}]: пользователь деактивирован")
            break
        except exceptions.TelegramAPIError:
            logger.exception(f"Target [ID:{user_id}]: ошибка API Telegram")
            break

        await asyncio.sleep(delay)

    return sent_any


@logger.catch
async def broadcast_message_to_users(
    text: str,
    users_list: list[int],
    disable_notification: bool = False,
    parse_mode: str = ParseMode.HTML,
    delay: float = 0.05,
) -> int:
    """
    Broadcasts a message to a list of users with rate limiting and error handling
    Rate limiting: 20 messages per second by default (0.05 sec) (Limit: 30 messages per second (0.33 sec))

    :param text: The message text to send
    :param users_list: A list of Telegram user IDs
    :param disable_notification: If True, sends the message silently
    :param parse_mode: The parse mode for the message (e.g., "html")
    :param delay: Delay in seconds between sending messages (default is 0.05)
    :return: The count of successfully sent messages
    """
    count = 0
    failed_users = []

    try:
        for user_id in users_list:
            try:
                if await send_message_to_user(
                    user_id,
                    text,
                    disable_notification=disable_notification,
                    parse_mode=parse_mode,
                ):
                    count += 1
                else:
                    failed_users.append(user_id)
            except Exception as e:
                logger.error(f"Error sending message to user [ID:{user_id}]: {e}")
                failed_users.append(user_id)

            await asyncio.sleep(delay)

    finally:
        logger.info(f"{count} messages successfully sent")
        if failed_users:
            logger.warning(f"Failed to send messages to {len(failed_users)} users: {failed_users}")

    return count


def split_into_messages(header: str, separator: str, items: list[str], max_length: int = 4096) -> list[str]:
    """
    Splits a list of text items into Telegram messages based on a maximum byte length
    If any message exceeds the limit, it is split into smaller messages while preserving formatting

    :param header: The header to prepend to the first message
    :param separator: The separator between items in a message
    :param items: A list of text items to include in the messages
    :param max_length: The maximum byte length of a message
    :return: A list of messages
    """

    # TODO: if item_length > max_length

    messages = []
    current_message = header  # Start with the header as the first message
    separator_length = len(separator.encode("utf-8"))

    for item in items:
        item_length = len(item.encode("utf-8"))
        current_length = len(current_message.encode("utf-8"))

        # If the item is small enough, add it to the current message
        if current_length + item_length + separator_length > max_length:
            # If adding the item would exceed the max length, split the current message
            messages.append(current_message.strip())
            current_message = item
        else:
            if current_message != header:
                current_message += separator
            current_message += item

    # Add the last message if necessary
    if current_message.strip():
        messages.append(current_message.strip())

    return messages


@logger.catch
async def pin_message(
    bot: Bot,
    username: str,
    callback_message: Message,
    chat_id: int,
    message_id: int,
    disable_notification: bool = False,
) -> None:

    try:
        await bot.pin_chat_message(
            chat_id=chat_id,
            message_id=message_id,
            disable_notification=disable_notification,
        )
        logger.info("[{username}]: The message (id={message_id}) in chat {chat_id} is pinned")
    except TelegramBadRequest as e:
        if e.message != "Bad Request: not enough rights to manage pinned messages in the chat":
            raise e
        logger.warning(f"[{username}]: Недостаточно прав для закрепления сообщения в чате")
        await callback_message.answer(
            "Ошибка при закреплении: для закрепления сообщения в чате не достаточно прав бота - повысьте права бота в чате"
        )
