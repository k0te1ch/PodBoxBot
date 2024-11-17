
from aiogram import F, Router
from aiogram.types import CallbackQuery
from config import FILES_PATH, FTP_LOGIN, FTP_PASSWORD, FTP_SERVER
from filters.dispatcher_filters import IsAdmin, IsPrivate
from loguru import logger
from services.keyboards import keyboards
from utils.FTP_methods import check_file_FTP, uploadToFTP

router = Router(name="ftp_handler")
router.message.filter(IsPrivate, IsAdmin)

#TODO: LOGGING and refactoring (in future)
@router.callback_query(F.data == "FTPMenu")
async def FTP_menu(callback: CallbackQuery, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: FTPMenu")

    await callback.message.edit_reply_markup(reply_markup=keyboards["podcast_handler"][language].FTPMenu)
    return await callback.answer()


#TODO: LOGGING and refactoring (in future)
@router.callback_query(F.data == "FTP_upload")
async def upload_FTP(callback: CallbackQuery, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: FTP_upload")
    if not await check_file_FTP(callback.message.audio.file_name, FTP_SERVER, FTP_LOGIN, FTP_PASSWORD):
        await uploadToFTP(
            f"{FILES_PATH}/{callback.message.audio.file_name}",
            callback.message.audio.file_name,
            FTP_SERVER,
            FTP_LOGIN,
            FTP_PASSWORD,
        )
    else:
        logger.opt(colors=True).debug(f"[<y>{username}</y>]: Файл уже загружен")
        return callback.answer("Файл уже загружен", show_alert=True)

    if await check_file_FTP(callback.message.audio.file_name, FTP_SERVER, FTP_LOGIN, FTP_PASSWORD):
        logger.opt(colors=True).debug(f"[<y>{username}</y>]: Загружено на FTP")
        #TODO: добавить уведомление
    else:
        logger.opt(colors=True).debug(f"[<y>{username}</y>]: <r>Ошибка при загрузке на FTP</r>")
        await upload_FTP(callback, username)
    return await callback.answer(text="Файл успешно загружен на FTP", show_alert=True)  #TODO: context
