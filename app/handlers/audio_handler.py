from aiogram import Bot, Router, F
from aiogram.types import CallbackQuery
from loguru import logger

from config import FORWARD_CHAT_ID
from filters.dispatcher_filters import IsAdmin, IsPrivate
from services import context
from services.keyboards import keyboards
from utils.podcast_methods import generate_podcast_text
from utils.validators import validate_template


router = Router(name="audio_handler")
router.message.filter(IsPrivate, IsAdmin)

#TODO: LOGGING and refactoring (in future)
@router.callback_query(F.data == "audioMenu")
async def audio_menu(callback: CallbackQuery, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: AudioMenu")

    if "rz" in callback.message.audio.file_name:
        await callback.message.edit_reply_markup(
            reply_markup=keyboards["podcast_handler"][language].audioMenuMain,
        )
    else:
        await callback.message.edit_reply_markup(
            reply_markup=keyboards["podcast_handler"][language].audioMenuPost,
        )

    return await callback.answer()

@router.callback_query(F.data == "fwd_verify")
async def forward_verify(callback: CallbackQuery, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Forwarding canceled")

    await callback.answer(text="Вы выбрали переслать сообщение в чат, переслать?", show_alert=True, cache_time=60)

    return await callback.message.edit_reply_markup(
        reply_markup=keyboards["podcast_handler"][language].verify
    )


@router.callback_query(F.data == "fwd_verify_no")
async def forward_no(callback: CallbackQuery, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Forwarding canceled")

    await callback.answer("Отменено")

    return await callback.message.edit_reply_markup(reply_markup=keyboards["podcast_handler"][language].audioMenuMain)



@router.callback_query(F.data == "fwd_verify_yes")
async def forward_yes(callback: CallbackQuery, bot: Bot, language: str, username: str):
    logger.opt(colors=True).debug(f"[<y>{username}</y>]: Forwarding to chat {FORWARD_CHAT_ID}")

    info = validate_template(callback.message.reply_to_message.text)
    if info == None:
        logger.opt(colors=True).debug(f"[<y>{username}</y>]: Invalid input in forward_yes")
        return await callback.answer(context[language].invalid_input, show_alert=True)

    podcast_text = generate_podcast_text(info) # TODO: ТЕСТЫ ДЛЯ СЛИШКОМ БОЛЬШОЙ ТЕКСТ И СЛИШКОМ МЕЛКИЙ

    await bot.send_audio(chat_id=FORWARD_CHAT_ID, audio=callback.message.audio.file_id, caption=podcast_text)

    logger.opt(colors=True).success(f"[<y>{username}</y>]: Success forward to chat")
    await callback.message.edit_reply_markup(reply_markup=keyboards["podcast_handler"][language].audioMenuMain)
    return await callback.answer("Переслали в чат!")
