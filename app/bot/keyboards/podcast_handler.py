from aiogram.types import InlineKeyboardButton, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from services import context


class ru:
    lang = "ru"

    # TODO: PREBUILD BUTTONS
    cancel = ReplyKeyboardBuilder()
    type_episode = ReplyKeyboardBuilder()

    cancel.add(KeyboardButton(text=context[lang].cancel))
    cancel = cancel.as_markup(resize_keyboard=True)

    type_episode.row(
        KeyboardButton(text=context[lang].main_episode),
        KeyboardButton(text=context[lang].episode_aftershow),
    )
    type_episode = type_episode.as_markup(resize_keyboard=True)

    audio_menu_main = InlineKeyboardBuilder()
    audio_menu_main.add(InlineKeyboardButton(text="FTP", callback_data="FTP_menu"))
    audio_menu_main.add(InlineKeyboardButton(text="Сайт", callback_data="WP_menu"))
    audio_menu_main.row(
        InlineKeyboardButton(text="Переслать в чат", callback_data="fwd_verify")
    )
    audio_menu_main = audio_menu_main.as_markup()

    verify = InlineKeyboardBuilder()
    verify.row(
        InlineKeyboardButton(text="Подтвердить ✅", callback_data="fwd_verify_yes")
    )
    verify.row(InlineKeyboardButton(text="Отмена ❌", callback_data="fwd_verify_no"))
    verify = verify.as_markup()

    audio_menu_post = InlineKeyboardBuilder()
    audio_menu_post.add(InlineKeyboardButton(text="FTP", callback_data="FTP_menu"))
    audio_menu_post = audio_menu_post.as_markup()

    FTP_menu = InlineKeyboardBuilder()
    FTP_menu.row(
        InlineKeyboardButton(
            text="Загрузить подкаст на FTP", callback_data="FTP_upload"
        )
    )
    FTP_menu.row(
        InlineKeyboardButton(text=context[lang].back, callback_data="audio_menu")
    )
    FTP_menu = FTP_menu.as_markup()

    WP_menu = InlineKeyboardBuilder()
    WP_menu.row(
        InlineKeyboardButton(
            text="Загрузить подкаст на сайт", callback_data="WP_upload"
        )
    )
    WP_menu.row(
        InlineKeyboardButton(text=context[lang].back, callback_data="audio_menu")
    )
    WP_menu = WP_menu.as_markup()


class en:
    lang = "en"

    cancel = ReplyKeyboardBuilder()
    type_episode = ReplyKeyboardBuilder()

    cancel.add(KeyboardButton(text=context[lang].cancel))
    cancel = cancel.as_markup(resize_keyboard=True)

    type_episode.row(
        KeyboardButton(text=context[lang].main_episode),
        KeyboardButton(text=context[lang].episode_aftershow),
    )
    type_episode = type_episode.as_markup(resize_keyboard=True)

    audio_menu_main = InlineKeyboardBuilder()
    audio_menu_main.add(InlineKeyboardButton(text="FTP", callback_data="FTP_menu"))
    audio_menu_main.add(InlineKeyboardButton(text="Site", callback_data="WP_menu"))
    audio_menu_main.row(
        InlineKeyboardButton(text="Forward to chat", callback_data="forward_to_chat")
    )
    audio_menu_main = audio_menu_main.as_markup()

    verify = InlineKeyboardBuilder()
    verify.row(InlineKeyboardButton(text="Confirm ✅", callback_data="verify_yes"))
    verify.row(InlineKeyboardButton(text="Cancel ❌", callback_data="verify_no"))
    verify = verify.as_markup()

    audio_menu_post = InlineKeyboardBuilder()
    audio_menu_post.add(InlineKeyboardButton(text="FTP", callback_data="FTP_menu"))
    audio_menu_post = audio_menu_post.as_markup()

    FTP_menu = InlineKeyboardBuilder()
    FTP_menu.row(
        InlineKeyboardButton(text="Upload a podcast to FTP", callback_data="FTP_upload")
    )
    FTP_menu.row(
        InlineKeyboardButton(text=context[lang].back, callback_data="audio_menu")
    )
    FTP_menu = FTP_menu.as_markup()

    WP_menu = InlineKeyboardBuilder()
    WP_menu.row(
        InlineKeyboardButton(
            text="Upload the podcast to the website", callback_data="WP_upload"
        )
    )
    WP_menu.row(
        InlineKeyboardButton(text=context[lang].back, callback_data="audio_menu")
    )
    WP_menu = WP_menu.as_markup()
