import os
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message
from loguru import logger

from config import LOGS_ZIP_NAME
from filters.dispatcher_filters import IsAdmin, IsPrivate
from keyboards import KEYBOARDS
from services import context, keyboards
from utils.bot_methods import get_zip_logs, restart_bot, shutdown_bot

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)


@router.message(F.text, Command("admin"))
async def admin(msg: Message, username: str):
    """Handle the /admin command"""
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Admin panel called")
    return await msg.answer(
        context.AdminPanel.opened, reply_markup=KEYBOARDS.admin_panel_kb
    )


@router.callback_query(F.data == "bot_panel")
async def bot_panel(callback: CallbackQuery, username: str):
    """Handle the transition to the bot management panel"""
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Bot management panel selected")

    await callback.message.edit_text(
        "Bot operations", reply_markup=KEYBOARDS.bot_commands_kb
    )
    return callback.answer()


@router.callback_query(F.data == "shutdown_bot")
async def shutdown(callback: CallbackQuery, username: str):
    """Handle the bot shutdown command"""
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Bot shutdown initiated")
    logger.warning(f"User {username} is shutting down the bot")

    await callback.answer("Bot is shutting down", show_alert=True)
    await shutdown_bot()


@router.callback_query(F.data == "restart_bot")
async def restart(callback: CallbackQuery, username: str):
    """Handle the bot restart command"""
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Bot restart initiated")
    logger.warning(f"User {username} is restarting the bot")

    await callback.answer("Bot is restarting", show_alert=True)
    await restart_bot()


@router.callback_query(F.data == "admin_back")
async def back(callback: CallbackQuery, username: str):
    """Handle the return to the main admin panel menu"""
    logger.opt(colors=True).debug(
        f"[<y>{username}</y>]: Return to the main admin panel menu"
    )

    await callback.message.edit_text(
        context.AdminPanel.opened,
        reply_markup=keyboards.admin_panel_kb,
    )
    return await callback.answer()


@router.callback_query(F.data == "send_logs")
async def send_logs(callback: CallbackQuery, username: str):
    """Handle the request to send logs"""
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Request to send logs")

    log_zip = get_zip_logs(LOGS_ZIP_NAME)
    if not log_zip:
        logger.error("Failed to create logs archive")
        await callback.answer("Ошибка: Ошибка с созданием логов", show_alert=True)
        return

    await callback.message.reply_document(FSInputFile(log_zip, log_zip.name))
    logger.info(f"Logs sent to user {username}")

    if isinstance(log_zip, Path):
        log_zip.unlink()
        logger.debug(f"Logs archive {log_zip.name} deleted")

    return await callback.answer()


@router.callback_query(F.data == "tests_panel")
async def tests_panel(callback: CallbackQuery, username: str):
    """Handle the transition to the tests panel"""
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Tests panel selected")

    await callback.message.edit_text(
        "Test operations for the bot", reply_markup=KEYBOARDS.tests_commands_kb
    )
    return callback.answer()
