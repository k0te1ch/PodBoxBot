import os

from aiogram import F, Router, types
from loguru import logger

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
# router.message.filter(IsPrivate, IsAdmin)


@router.message(F.pinned_message)
async def delete_pinned_service_message(message: types.Message, bot):
    """Убирает служебное «... закрепил сообщение», но только своё.

    Бот сам закрепляет анонсы (utils.messaging.pin_message) и подчищает
    за собой уведомление. Закрепы, сделанные людьми, — их действие, стирать
    служебку за них нельзя.
    """
    if message.from_user is None or message.from_user.id != bot.id:
        return

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception as e:
        logger.warning(f"Failed to delete pinned service message: {e!r}")
