# TODO REBUILD THIS
#! BECAUSE IT ISN'T WORK!

from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, FSInputFile
from loguru import logger

from utils.bot_methods import shutdown_bot
from utils.context import context
from utils.dispatcher_filters import IsAdmin, IsPrivate
from utils.keyboards import keyboards
from aiogram import F, Router
from config import FILES_PATH, LOGS_PATH
import os
import glob
import zipfile


# TODO add callback fabric
router = Router(name="admin_panel")
router.message.filter(IsPrivate, IsAdmin)


@router.message(F.text, Command("admin_panel"))
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
async def sendLogs(callback: CallbackQuery, username: str):
    logger.opt(colors=True).debug(
        f"[<y>{username}</y>]: Send last log to admin through bot"
    )

    logFiles = sorted(filter(os.path.isfile, glob.glob(LOGS_PATH + "/*" + ".log")))

    logName = "logs.zip"  # TODO to env
    logZip = f"{FILES_PATH}/{logName}"
    with zipfile.ZipFile(f"{FILES_PATH}/logs.zip", mode="w") as archive:
        for fileName in logFiles:
            archive.write(fileName, f"logs/{os.path.split(fileName)[-1]}")

    await callback.message.reply_document(FSInputFile(logZip, logName))

    os.remove(logZip)

    return await callback.answer()
