"""Как достучаться до автора темы.

Личку бот открыть не может, пока человек сам ему не написал. Поэтому второй
путь — эфемерное сообщение в группе (Bot API 10.3): его видит только
получатель, а бот-администратор может отправить такое в любой момент.
"""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import EphemeralMessageParameters, ReplyParameters
from loguru import logger

from services.topics.models import Topic


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


async def notify_author(bot: Bot, topic: Topic, text: str) -> bool:
    """Сначала в личку, потом эфемерно в чат, откуда пришла тема."""
    user_id = topic.author.user_id
    if user_id is None:
        return False
    try:
        await bot.send_message(chat_id=user_id, text=text)
        return True
    except TelegramAPIError as error:
        logger.info(f"topic #{topic.id}: author {user_id} is not reachable in private: {error!r}")
    if topic.chat_id is None:
        return False
    return await send_ephemeral(bot, topic.chat_id, user_id, text)
