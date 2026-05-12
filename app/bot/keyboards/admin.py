from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services import context

# Кэш для созданных клавиатур
_keyboards_cache = {}


def _build_kb_for_lang(lang: str) -> dict:
    """Создаёт клавиатуры для указанного языка"""
    if lang in _keyboards_cache:
        return _keyboards_cache[lang]

    try:
        main_kb = InlineKeyboardBuilder()
        bot_commands_kb_builder = InlineKeyboardBuilder()

        for i in context[lang].admin_panel_main:
            main_kb.add(InlineKeyboardButton(text=i[0], callback_data=i[1]))

        for i in context[lang].bot_commands:
            bot_commands_kb_builder.add(InlineKeyboardButton(text=i[0], callback_data=i[1]))

        bot_commands_kb_builder.adjust(4)
        bot_commands_kb_builder.add(InlineKeyboardButton(text=context[lang].back, callback_data="back"))

        cache = {"main": main_kb.as_markup(), "bot_commands": bot_commands_kb_builder.as_markup()}
        _keyboards_cache[lang] = cache
        return cache
    except Exception:
        # Если context не инициализирован, возвращаем пустые клавиатуры
        return {"main": InlineKeyboardBuilder().as_markup(), "bot_commands": InlineKeyboardBuilder().as_markup()}


def get_admin_panel_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    """Получить клавиатуру административной панели"""
    return _build_kb_for_lang(lang)["main"]


def get_bot_commands_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    """Получить клавиатуру команд бота"""
    return _build_kb_for_lang(lang)["bot_commands"]


# Для совместимости со старым кодом
def admin_panel_kb() -> InlineKeyboardMarkup:
    return get_admin_panel_kb("ru")


def bot_commands_kb() -> InlineKeyboardMarkup:
    return get_bot_commands_kb("ru")


def tests_commands_kb() -> InlineKeyboardMarkup:
    """Клавиатура для тестовых команд"""
    return InlineKeyboardBuilder().as_markup()
