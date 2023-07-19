from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.context import context

#TODO Когда загружается бот, если кнопки используются, то мы их создаём и храним в памяти
#TODO Добавить типы во всех функции
#TODO Классы? Ты серьёзно? Надо переписать это дерьмо


class ru:
    lang = "ru"

    main = InlineKeyboardBuilder()
    bot_commands = InlineKeyboardBuilder()

    for i in context[lang].admin_panel_main:
        main.button(text=i[0], callback_data=i[1])

    main = main.as_markup()
    for i in context[lang].bot_commands:
        bot_commands.button(text=i[0], callback_data=i[1])
    bot_commands.adjust(4)
    bot_commands.button(text=context[lang].back, callback_data="back")
    bot_commands = bot_commands.as_markup()


class en:
    lang = "en"

    main = InlineKeyboardBuilder()
    bot_commands = InlineKeyboardBuilder()

    for i in context[lang].admin_panel_main:
        main.button(text=i[0], callback_data=i[1])

    main = main.as_markup()
    for i in context[lang].bot_commands:
        bot_commands.button(text=i[0], callback_data=i[1])
    bot_commands.adjust(4)
    bot_commands.button(text=context[lang].back, callback_data="back")
    bot_commands = bot_commands.as_markup()