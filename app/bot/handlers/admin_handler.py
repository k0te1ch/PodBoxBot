"""Кнопки админ-панели (дерево меню и команда /admin — в :mod:`handlers.menus`)."""

from pathlib import Path

from aiogram.types import FSInputFile
from loguru import logger
from sagenza_tgbot_sdk.menus import MenuContext

from config import LOGS_ZIP_NAME
from services.i18n import t
from utils.bot_methods import get_zip_logs, restart_bot
from utils.menu_context import username as username_of


async def restart(ctx: MenuContext):
    """Handle the bot restart command"""
    username = username_of(ctx)
    logger.warning(f"User {username} is restarting the bot")

    await ctx.answer(t("bot_restarting", ctx.locale), alert=True)
    restart_bot()


async def send_logs(ctx: MenuContext):
    """Handle the request to send logs"""
    username = username_of(ctx)
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Request to send logs")

    log_zip = get_zip_logs(LOGS_ZIP_NAME)
    if not log_zip:
        logger.error("Failed to create logs archive")
        await ctx.answer(t("logs_failed", ctx.locale), alert=True)
        return

    await ctx.message.reply_document(FSInputFile(log_zip, log_zip.name))
    logger.info(f"Logs sent to user {username}")

    if isinstance(log_zip, Path):
        log_zip.unlink()
        logger.debug(f"Logs archive {log_zip.name} deleted")
