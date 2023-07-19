
#TODO REBUILD THIS
#! BECAUSE IT ISN'T WORK!

from aiogram.filters import CommandStart, Text, Command
from aiogram.types import ReplyKeyboardRemove, CallbackQuery
from loguru import logger
from utils.bot_methods import reload_bot, shutdown_bot

from bot import context, db, dp, keyboards
from utils.dispatcher_filters import ContextButton, IsPrivate, IsAdmin


@dp.message_handler(IsPrivate, IsAdmin, Command(["admin_panel"]))
async def start(msg, language):
    logger.opt(colors=True).debug(f"[<y>{msg.from_user.username}</y>]: Call admin panel")

    return await msg.answer(context[language].admin_panel_open, reply_markup=keyboards["admin"][language].main)


@dp.callback_query_handler(lambda msg: msg.data == "bot", IsPrivate, IsAdmin)
async def bot(callback: CallbackQuery, language):
    logger.opt(colors=True).debug(f"[<y>{callback.from_user.username}</y>]: Choose bot in admin panel")

    return await callback.message.edit_text("Операции над ботом", reply_markup=keyboards["admin"][language].bot_commands)


#TODO IN PROGRESS
@dp.callback_query_handler(lambda msg: msg.data == "restart_bot", IsPrivate, IsAdmin)
async def restart(callback: CallbackQuery, language):
    logger.opt(colors=True).debug(f"[<y>{callback.from_user.username}</y>]: Restart bot")
    
    await callback.answer()
    await callback.message.answer("Бот перезагружается", reply_markup=ReplyKeyboardRemove())
    #TODO
    await reload_bot()


@dp.callback_query_handler(lambda msg: msg.data == "shutdown_bot", IsPrivate, IsAdmin)
async def shutdown(callback: CallbackQuery, language):
    logger.opt(colors=True).debug(f"[<y>{callback.from_user.username}</y>]: Shutdown bot")
    
    await callback.answer()
    await callback.message.answer("Бот выключен", reply_markup=ReplyKeyboardRemove())
    #TODO
    await shutdown_bot()


@dp.callback_query_handler(lambda msg: msg.data == "back", IsPrivate, IsAdmin)
async def back(callback, language):
    logger.opt(colors=True).debug(f"[<y>{callback.from_user.username}</y>]: Call back to admin panel")

    await callback.answer()
    return await callback.message.edit_text(context[language].admin_panel_open, reply_markup=keyboards["admin"][language].main)