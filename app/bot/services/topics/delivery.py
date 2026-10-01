"""Как ответить автору так, чтобы чат этого не видел.

Эфемерное сообщение в группе (Bot API 10.3) видит только получатель, а
бот-администратор может отправить такое в любой момент.
"""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import EphemeralMessageParameters, ReplyParameters
from loguru import logger


async def send_ephemeral(bot: Bot, chat_id: int, user_id: int, text: str, reply_to: int | None = None) -> bool:
    """Эфемерное сообщение участнику группы; ``False``, если Telegram отказал."""
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_parameters=ReplyParameters(message_id=reply_to, allow_sending_without_reply=True)
            if reply_to is not None
            else None,
            ephemeral_message_parameters=EphemeralMessageParameters(receiver_user_id=user_id),
        )
    except TelegramAPIError as error:
        logger.info(f"ephemeral message to {user_id} in {chat_id} failed: {error!r}")
        return False
    return True
