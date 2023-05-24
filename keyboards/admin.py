from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

from bot import context



class ru:
    lang = "ru"

    main = InlineKeyboardMarkup(resize_keyboard=True)
    bot_commands = InlineKeyboardMarkup(resize_keyboard=True)

    for i in context[lang].admin_panel_main:
        main.add(InlineKeyboardButton(i[0], callback_data=i[1]))

    tmp = []
    for i in context[lang].bot_commands:
        tmp.append(InlineKeyboardButton(i[0], callback_data=i[1]))
    bot_commands.row(*tmp)
    bot_commands.add(InlineKeyboardButton(context[lang].back, callback_data="back"))


class en:
    lang = "en"

    main = InlineKeyboardMarkup(resize_keyboard=True)
    bot_commands = InlineKeyboardMarkup(resize_keyboard=True)

    for i in context[lang].admin_panel_main:
        main.add(InlineKeyboardButton(i[0], callback_data=i[1]))

    tmp = []
    for i in context[lang].bot_commands:
        tmp.append(InlineKeyboardButton(i[0], callback_data=i[1]))
    bot_commands.row(*tmp)
    bot_commands.add(InlineKeyboardButton(context[lang].back, callback_data="back"))