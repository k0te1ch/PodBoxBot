import os

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from loguru import logger

from config import FORWARD_CHAT_ID
from filters.dispatcher_filters import IsAdmin, IsPrivate
from services import context, keyboards
from utils.bot_methods import pin_message
from utils.podcast_methods import generate_podcast_text
from utils.template_store import load as load_template_info

router = Router(name=os.path.splitext(os.path.basename(__file__))[0])
router.message.filter(IsPrivate, IsAdmin)


def get_keyboard(language: str, key: str):
    """Возвращает нужную клавиатуру по ключу"""
    return keyboards["podcast_handler"][language][key]


@router.callback_query(F.data == "audio_menu")
async def audio_menu(callback: CallbackQuery, language: str, username: str):
    """Обработчик открытия аудио-меню"""
    logger.debug(f"[{username}]: Opened Audio_Menu")

    keyboard_key = "audio_menu_main" if "rz" in callback.message.audio.file_name else "audio_menu_post"

    logger.debug(f'[{username}]: keyboard_key = "{keyboard_key}"')

    await callback.message.edit_reply_markup(reply_markup=get_keyboard(language, keyboard_key))
    await callback.answer()


@router.callback_query(F.data == "fwd_verify")
async def forward_verify(callback: CallbackQuery, language: str, username: str):
    """Обработчик запроса на пересылку"""
    logger.debug(f"[{username}]: Forward verification requested")

    await callback.answer(
        text="Вы выбрали переслать сообщение в чат, переслать?",
        show_alert=True,
        cache_time=60,
    )
    await callback.message.edit_reply_markup(reply_markup=get_keyboard(language, "verify"))


@router.callback_query(F.data == "fwd_verify_no")
async def forward_no(callback: CallbackQuery, language: str, username: str):
    """Обработчик отказа от пересылки"""
    logger.debug(f"[{username}]: Forwarding canceled")

    await callback.answer("Отменено")
    await callback.message.edit_reply_markup(reply_markup=get_keyboard(language, "audio_menu_main"))


@router.callback_query(F.data == "fwd_verify_yes")
async def forward_yes(callback: CallbackQuery, bot: Bot, language: str, username: str):
    """Обработчик подтверждения пересылки"""
    logger.debug(f"[{username}]: Forwarding to chat {FORWARD_CHAT_ID}")

    try:
        file_name = callback.message.audio.file_name
        stored = await load_template_info(file_name)
        if stored is None:
            logger.warning(f"[{username}]: template info not found for {file_name}")
            return await callback.answer(context[language].invalid_input, show_alert=True)

        info = stored["info"]

        # Генерация текста подкаста
        podcast_text = generate_podcast_text(info)

        # Пересылка аудио в указанный чат
        forward_message = await bot.send_audio(
            chat_id=FORWARD_CHAT_ID,
            audio=callback.message.audio.file_id,
            caption=podcast_text,
        )

        disable_notification = False  # TODO: to settings

        # Закрепляем аудио в чате
        await pin_message(
            bot,
            username,
            callback.message,
            FORWARD_CHAT_ID,
            forward_message.message_id,
            disable_notification=disable_notification,
        )

        logger.success(f"[{username}]: Successfully forwarded audio")
        await callback.message.edit_reply_markup(reply_markup=get_keyboard(language, "audio_menu_main"))
        await callback.answer("Переслали в чат!")

    except Exception as e:
        logger.error(f"[{username}]: Error in forward_yes - {e}")
        await callback.answer("Ошибка при пересылке, попробуйте позже", show_alert=True)
