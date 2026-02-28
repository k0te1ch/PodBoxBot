from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services import context

# TODO: Когда загружается бот, если кнопки используются, то мы их создаём и храним в памяти
# TODO: Добавить типы во всех функции
# TODO: Классы? Ты серьёзно? Надо переписать это дерьмо


class ru:
    lang = "ru"

    main = InlineKeyboardBuilder()
    bot_commands = InlineKeyboardBuilder()

    for i in context[lang].admin_panel_main:
        main.add(InlineKeyboardButton(text=i[0], callback_data=i[1]))

    main = main.as_markup()
    for i in context[lang].bot_commands:
        bot_commands.add(InlineKeyboardButton(text=i[0], callback_data=i[1]))
    bot_commands.adjust(4)
    bot_commands.add(
        InlineKeyboardButton(text=context[lang].back, callback_data="back")
    )
    bot_commands = bot_commands.as_markup()


class en:
    lang = "en"

    main = InlineKeyboardBuilder()
    bot_commands = InlineKeyboardBuilder()

    for i in context[lang].admin_panel_main:
        main.add(InlineKeyboardButton(text=i[0], callback_data=i[1]))

    main = main.as_markup()
    for i in context[lang].bot_commands:
        bot_commands.add(InlineKeyboardButton(text=i[0], callback_data=i[1]))
    bot_commands.adjust(4)
    bot_commands.add(
        InlineKeyboardButton(text=context[lang].back, callback_data="back")
    )
    bot_commands = bot_commands.as_markup()

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


from aiogram.utils.keyboard import InlineKeyboardBuilder

from services import context


# Клавиатура для панели
def admin_panel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for text, callback_data in context.AdminPanel.panels:
        kb.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    return kb.as_markup()


# Клавиатура для команд бота
def bot_commands_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for text, callback_data in context.AdminPanel.bot_commands:
        kb.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    return kb.as_markup()


# Клавиатура для тестовых новостей
def tests_commands_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for text, callback_data in context.AdminPanel.test_news_commands:
        kb.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    return kb.as_markup()
