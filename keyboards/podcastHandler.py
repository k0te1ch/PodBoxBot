from aiogram.types import KeyboardButton, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from utils.context import context


class ru:
    lang = "ru"

    #TODO PREBUILD BUTTONS
    cancel = ReplyKeyboardBuilder()
    typeEpisode = ReplyKeyboardBuilder()

    cancel.add(KeyboardButton(text = context[lang].cancel))
    cancel = cancel.as_markup(resize_keyboard=True)

    typeEpisode.row(KeyboardButton(text = context[lang].main_episode), KeyboardButton(text = context[lang].episode_aftershow))
    typeEpisode = typeEpisode.as_markup(resize_keyboard=True)

    audioMenu = InlineKeyboardBuilder()
    audioMenu.add(InlineKeyboardButton(text="FTP", callback_data="FTPMenu"))
    audioMenu = audioMenu.as_markup()

    FTPMenu = InlineKeyboardBuilder()
    FTPMenu.add(InlineKeyboardButton(text="Загрузить подкаст на FTP", callback_data="FTP_upload"))
    FTPMenu.add(InlineKeyboardButton(text=context[lang].back, callback_data="audioMenu"))
    FTPMenu = FTPMenu.as_markup()


class en:
    lang = "en"

    cancel = ReplyKeyboardBuilder()
    typeEpisode = ReplyKeyboardBuilder()

    cancel.add(KeyboardButton(text = context[lang].cancel))
    cancel = cancel.as_markup(resize_keyboard=True)

    typeEpisode.row(KeyboardButton(text = context[lang].main_episode), KeyboardButton(text = context[lang].episode_aftershow))
    typeEpisode = typeEpisode.as_markup(resize_keyboard=True)