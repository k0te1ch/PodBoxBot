from aiogram.types import KeyboardButton, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from services.context import context


class ru:
    lang = "ru"

    #TODO: PREBUILD BUTTONS
    cancel = ReplyKeyboardBuilder()
    typeEpisode = ReplyKeyboardBuilder()

    cancel.add(KeyboardButton(text=context[lang].cancel))
    cancel = cancel.as_markup(resize_keyboard=True)

    typeEpisode.row(
        KeyboardButton(text=context[lang].main_episode),
        KeyboardButton(text=context[lang].episode_aftershow),
    )
    typeEpisode = typeEpisode.as_markup(resize_keyboard=True)

    audioMenuMain = InlineKeyboardBuilder()
    audioMenuMain.add(InlineKeyboardButton(text="FTP", callback_data="FTPMenu"))
    audioMenuMain.add(InlineKeyboardButton(text="Сайт", callback_data="WPMenu"))
    audioMenuMain.row(InlineKeyboardButton(text="Переслать в чат", callback_data="fwd_verify"))
    audioMenuMain = audioMenuMain.as_markup()

    verify = InlineKeyboardBuilder()
    verify.row(InlineKeyboardButton(text="Подтвердить ✅", callback_data="fwd_verify_yes"))
    verify.row(InlineKeyboardButton(text="Отмена ❌", callback_data="fwd_verify_no"))
    verify = verify.as_markup()

    audioMenuPost = InlineKeyboardBuilder()
    audioMenuPost.add(InlineKeyboardButton(text="FTP", callback_data="FTPMenu"))
    audioMenuPost = audioMenuPost.as_markup()

    FTPMenu = InlineKeyboardBuilder()
    FTPMenu.row(
        InlineKeyboardButton(
            text="Загрузить подкаст на FTP", callback_data="FTP_upload"
        )
    )
    FTPMenu.row(
        InlineKeyboardButton(text=context[lang].back, callback_data="audioMenu")
    )
    FTPMenu = FTPMenu.as_markup()

    WPMenu = InlineKeyboardBuilder()
    WPMenu.row(
        InlineKeyboardButton(
            text="Загрузить подкаст на сайт", callback_data="WP_upload"
        )
    )
    WPMenu.row(InlineKeyboardButton(text=context[lang].back, callback_data="audioMenu"))
    WPMenu = WPMenu.as_markup()


class en:
    lang = "en"

    cancel = ReplyKeyboardBuilder()
    typeEpisode = ReplyKeyboardBuilder()

    cancel.add(KeyboardButton(text=context[lang].cancel))
    cancel = cancel.as_markup(resize_keyboard=True)

    typeEpisode.row(
        KeyboardButton(text=context[lang].main_episode),
        KeyboardButton(text=context[lang].episode_aftershow),
    )
    typeEpisode = typeEpisode.as_markup(resize_keyboard=True)

    audioMenuMain = InlineKeyboardBuilder()
    audioMenuMain.add(InlineKeyboardButton(text="FTP", callback_data="FTPMenu"))
    audioMenuMain.add(InlineKeyboardButton(text="Site", callback_data="WPMenu"))
    audioMenuMain.row(InlineKeyboardButton(text="Forward to chat", callback_data="forward_to_chat"))
    audioMenuMain = audioMenuMain.as_markup()

    verify = InlineKeyboardBuilder()
    verify.row(InlineKeyboardButton(text="Confirm ✅", callback_data="verify_yes"))
    verify.row(InlineKeyboardButton(text="Cancel ❌", callback_data="verify_no"))
    verify = verify.as_markup()

    audioMenuPost = InlineKeyboardBuilder()
    audioMenuPost.add(InlineKeyboardButton(text="FTP", callback_data="FTPMenu"))
    audioMenuPost = audioMenuPost.as_markup()

    FTPMenu = InlineKeyboardBuilder()
    FTPMenu.row(InlineKeyboardButton(text="Upload a podcast to FTP", callback_data="FTP_upload"))
    FTPMenu.row(InlineKeyboardButton(text=context[lang].back, callback_data="audioMenu"))
    FTPMenu = FTPMenu.as_markup()

    WPMenu = InlineKeyboardBuilder()
    WPMenu.row(InlineKeyboardButton(text="Upload the podcast to the website", callback_data="WP_upload"))
    WPMenu.row(InlineKeyboardButton(text=context[lang].back, callback_data="audioMenu"))
    WPMenu = WPMenu.as_markup()
