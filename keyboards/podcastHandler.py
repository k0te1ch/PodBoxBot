from aiogram.types import KeyboardButton, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from utils.context import context


class ru:
    lang = "ru"

    # TODO PREBUILD BUTTONS
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
    audioMenuMain = audioMenuMain.as_markup()

    audioMenuPost = InlineKeyboardBuilder()
    audioMenuPost.add(InlineKeyboardButton(text="FTP", callback_data="FTPMenu"))
    audioMenuPost = audioMenuPost.as_markup()

    FTPMenu = InlineKeyboardBuilder()
    FTPMenu.add(
        InlineKeyboardButton(
            text="Загрузить подкаст на FTP", callback_data="FTP_upload"
        )
    )
    FTPMenu.add(
        InlineKeyboardButton(text=context[lang].back, callback_data="audioMenu")
    )
    FTPMenu = FTPMenu.as_markup()

    WPMenu = InlineKeyboardBuilder()
    WPMenu.add(
        InlineKeyboardButton(
            text="Загрузить подкаст на сайт", callback_data="WP_upload"
        )
    )
    WPMenu.add(InlineKeyboardButton(text=context[lang].back, callback_data="audioMenu"))
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
