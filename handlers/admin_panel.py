#TODO REBUILD THIS
#! BECAUSE IT ISN'T WORK!

from aiogram.filters import Command, Text
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from loguru import logger

from utils.bot_methods import shutdown_bot
from utils.context import context
from utils.dispatcher_filters import ContextButton, IsAdmin, IsPrivate
from utils.keyboards import keyboards
from aiogram import F, Router, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData

#TODO add callback fabric
router = Router(name="admin_panel")
router.message.filter(IsPrivate, IsAdmin)


@router.message(F.text, Command("admin_panel"))
async def start(msg: Message, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Call admin panel")
    return await msg.answer(context["ru"].admin_panel_open, reply_markup=keyboards["admin"][language].main)


@router.callback_query(Text("bot"))
async def bot(callback: CallbackQuery, language: str, username: str):
    logger.opt(
        colors=True).debug(f"[<y>{username}</y>]: Choose bot in admin panel")

    return await callback.message.edit_text(
        "Операции над ботом",
        reply_markup=keyboards["admin"][language].bot_commands)


#TODO IN PROGRESS
@router.callback_query(Text("restart_bot"))
async def restart(callback: CallbackQuery, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Restart bot")

    await callback.answer()
    await callback.message.answer("Бот перезагружается",
                                  reply_markup=ReplyKeyboardRemove())
    #TODO
    await shutdown_bot()


@router.callback_query(Text("back"))
async def back(callback: CallbackQuery, language: str, username: str):
    logger.opt(
        colors=True).debug(f"[<y>{username}</y>]: Call back to admin panel")

    await callback.answer()
    return await callback.message.edit_text(
        context[language].admin_panel_open,
        reply_markup=keyboards["admin"][language].main)
