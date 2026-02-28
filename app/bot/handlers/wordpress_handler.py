import os

from aiogram import F, Router
from aiogram.types import CallbackQuery
from loguru import logger

from filters.dispatcher_filters import IsAdmin, IsPrivate
from services import context, keyboards
from utils.validators import validate_template
from utils.wordpress import WordPress

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)


@router.callback_query(F.data == "WPMenu")
async def WP_menu(callback: CallbackQuery, language: str, username: str) -> None:
    logger.bind(username=username).debug("Открыто меню WordPress")

    await callback.message.edit_reply_markup(
        reply_markup=keyboards["podcast_handler"][language].WPMenu
    )
    await callback.answer()


@router.callback_query(F.data == "WP_upload")
async def upload_WP(callback: CallbackQuery, language: str, username: str) -> None:
    logger.bind(username=username).debug("Начата загрузка в WordPress")

    message = callback.message.reply_to_message
    if not message or not message.text:
        return await callback.answer(context[language].invalid_input, show_alert=True)

    info = validate_template(message.text)
    if not info:
        logger.bind(username=username).debug("Ошибка валидации шаблона")
        return await callback.answer(context[language].invalid_input, show_alert=True)

    audio = callback.message.audio
    info.update(
        {
            "slug": audio.file_name.removesuffix(".mp3"),
            "duration": audio.duration,
        }
    )

    with WordPress() as wp:
        wp.upload_post(info)

    logger.bind(username=username).debug("Пост загружен в черновики")
    await callback.answer("Пост успешно сохранён в черновики", show_alert=True)
