from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services import context


def _build(lang: str):
    _main = InlineKeyboardBuilder()
    for i in context[lang].admin_panel_main:
        _main.add(InlineKeyboardButton(text=i[0], callback_data=i[1]))

    _bot_commands = InlineKeyboardBuilder()
    for i in context[lang].bot_commands:
        _bot_commands.add(InlineKeyboardButton(text=i[0], callback_data=i[1]))
    _bot_commands.adjust(4)
    _bot_commands.add(InlineKeyboardButton(text=context[lang].back, callback_data="back"))

    class _Lang:
        main = _main.as_markup()
        bot_commands = _bot_commands.as_markup()

    return _Lang


ru = _build("ru")
en = _build("en")


def admin_panel_kb() -> InlineKeyboardMarkup:
    return ru.main


def bot_commands_kb() -> InlineKeyboardMarkup:
    return ru.bot_commands


def tests_commands_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardBuilder().as_markup()
