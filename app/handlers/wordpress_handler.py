
from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger

from services.context import context
from filters.dispatcher_filters import IsAdmin, IsPrivate
from services.keyboards import keyboards
from utils.validators import validate_template


router = Router(name="wordpress_handler")
router.message.filter(IsPrivate, IsAdmin)

@router.callback_query(F.data == "WPMenu")
async def WP_menu(callback: CallbackQuery, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: WPMenu")

    await callback.message.edit_reply_markup(reply_markup=keyboards["podcast_handler"][language].WPMenu)
    return await callback.answer()


@router.callback_query(F.data == "WP_upload")
async def upload_WP(callback: CallbackQuery, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: WP_upload")

    info = validate_template(callback.message.reply_to_message.text)
    if info == None:
        logger.opt(colors=True).debug(f"[<y>{username}</y>]: Invalid input in WP_upload")
        return await callback.answer(context[language].invalid_input, show_alert=True)

    info["slug"] = callback.message.audio.file_name.replace(".mp3", "")
    info["duration"] = callback.message.audio.duration

    from utils.wordpress import wordpress

    with wordpress as wp:
        wp.upload_post(info)

    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Загружено")
    return await callback.answer(text="Пост успешно сохранён в черновики", show_alert=True)
