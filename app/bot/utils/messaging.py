"""Отправка сообщений в Telegram: рассылка, нарезка под лимит, закреп.

Выделено из ``bot_methods``: тот перевалил за 500 строк и держал три
несвязанные темы сразу.
"""

import asyncio

from aiogram import Bot, exceptions
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from loguru import logger


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
    text: str | list[str],
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


def _split_oversized(item: str, max_length: int) -> list[str]:
    """Режет один элемент по границам символов так, чтобы каждый кусок
    укладывался в ``max_length`` байт.

    Разметку не учитывает: HTML-тег может попасть на стык кусков. Для
    аккуратно нарезанных секций (``get_release_note``) этот путь не нужен —
    он страховка от одиночной строки, которая длиннее лимита сама по себе.
    """
    chunks: list[str] = []
    current = ""
    current_length = 0

    for char in item:
        char_length = len(char.encode("utf-8"))
        if current_length + char_length > max_length:
            chunks.append(current)
            current, current_length = "", 0
        current += char
        current_length += char_length

    chunks.append(current)
    return chunks


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

    messages = []
    current_message = header  # Start with the header as the first message
    separator_length = len(separator.encode("utf-8"))

    for item in items:
        item_length = len(item.encode("utf-8"))
        current_length = len(current_message.encode("utf-8"))

        if item_length > max_length:
            # Элемент не влезает в сообщение даже один. Раньше он уезжал в
            # результат целиком и Telegram отвечал 'message is too long';
            # режем его на куски и продолжаем набор с последнего.
            if current_message.strip():
                messages.append(current_message.strip())
            *head, current_message = _split_oversized(item, max_length)
            messages.extend(chunk.strip() for chunk in head if chunk.strip())
            continue

        # If the item is small enough, add it to the current message
        if current_length + item_length + separator_length > max_length:
            # If adding the item would exceed the max length, split the current message.
            # Skip flushing if current is empty (header=="" and no items added yet) —
            # иначе в начало рассылки лез пустой message и TG отвечал
            # 'Bad Request: message text is empty'.
            if current_message.strip():
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
    chat_id: int | str,
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
