from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

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


class en:
    lang = "en"

    cancel = ReplyKeyboardBuilder()
    typeEpisode = ReplyKeyboardBuilder()

    cancel.add(KeyboardButton(text = context[lang].cancel))
    cancel = cancel.as_markup(resize_keyboard=True)

    typeEpisode.row(KeyboardButton(text = context[lang].main_episode), KeyboardButton(text = context[lang].episode_aftershow))
    typeEpisode = typeEpisode.as_markup(resize_keyboard=True)