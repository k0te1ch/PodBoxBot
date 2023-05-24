from aiogram.types import ReplyKeyboardMarkup

from bot import context


class ru:
    lang = "ru"

    #TODO PREBUILD BUTTONS
    cancel = ReplyKeyboardMarkup(resize_keyboard=True)
    typeEpisode = ReplyKeyboardMarkup(resize_keyboard=True)

    cancel.add(context[lang].cancel)

    typeEpisode.row(context[lang].main_episode, context[lang].episode_aftershow)


class en:
    lang = "en"

    cancel = ReplyKeyboardMarkup(resize_keyboard=True)
    typeEpisode = ReplyKeyboardMarkup(resize_keyboard=True)

    cancel.add(context[lang].cancel)

    typeEpisode.row(context[lang].main_episode, context[lang].episode_aftershow)