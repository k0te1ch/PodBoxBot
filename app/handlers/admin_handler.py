#TODO: REBUILD THIS
#! BECAUSE IT ISN'T WORK!

from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, FSInputFile
from loguru import logger

from pathlib import Path
from config import LOGS_ZIP_NAME
from utils.bot_methods import shutdown_bot
from services.context import context
from filters.dispatcher_filters import IsAdmin, IsPrivate
from services.keyboards import keyboards
from aiogram import F, Router
from utils.bot_methods import get_zip_logs


#TODO: add callback fabric
router = Router(name="admin_handler")
router.message.filter(IsPrivate, IsAdmin)


@router.message(F.text, Command("admin"))
async def start(msg: Message, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Call admin panel")
    return await msg.answer(
        context["ru"].admin_panel_open, reply_markup=keyboards["admin"][language].main
    )


@router.callback_query(F.data == "botPanel")
async def botPanel(callback: CallbackQuery, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Choose bot in admin panel")

    await callback.message.edit_text(
        "Операции над ботом", reply_markup=keyboards["admin"][language].bot_commands
    )

    return callback.answer()


@router.callback_query(F.data == "shutdown_bot")
async def shutdown(callback: CallbackQuery, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Shutdown bot")

    await callback.answer("Бот выключается", show_alert=True)

    await shutdown_bot()


@router.callback_query(F.data == "back")
async def back(callback: CallbackQuery, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Back to admin panel")

    await callback.message.edit_text(
        context[language].admin_panel_open,
        reply_markup=keyboards["admin"][language].main,
    )

    return await callback.answer()


@router.callback_query(F.data == "send_logs")
async def send_logs(callback: CallbackQuery, username: str):
    logger.opt(colors=True).debug(
        f"[<y>{username}</y>]: Send last log to admin through bot"
    )

    log_zip = get_zip_logs(LOGS_ZIP_NAME)
    await callback.message.reply_document(FSInputFile(log_zip, log_zip.name))

    if isinstance(log_zip, Path):
        log_zip.unlink()

    return await callback.answer()
