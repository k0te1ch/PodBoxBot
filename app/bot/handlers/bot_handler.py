import os

from aiogram import F, Router, types
from aiogram.filters import CommandObject

from filters.dispatcher_filters import IsAdmin, IsPrivate

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
# router.message.filter(IsPrivate, IsAdmin)

# Предположим, что переменная из config называется DELETE_PINNED_SERVICE_MESSAGE
# from config import DELETE_PINNED_SERVICE_MESSAGE


# TODO: ПРОВЕРКА НА ТО, ЧТОБЫ ЗАКРЕПИЛ БОТ!
@router.message(F.pinned_message)
async def delete_pinned_service_message(message: types.Message, bot):
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception as e:
        print(f"Failed to delete pinned service message: {e}")
