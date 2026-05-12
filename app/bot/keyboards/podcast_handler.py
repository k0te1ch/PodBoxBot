from aiogram.types import InlineKeyboardButton, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from services import context

# Кэш для созданных клавиатур
_keyboards_cache = {}


def _build_kb_for_lang_podcast(lang: str) -> dict:
    """Создаёт клавиатуры для подкастов"""
    if lang in _keyboards_cache:
        return _keyboards_cache[lang]

    try:
        # Cancel keyboard
        cancel_kb = ReplyKeyboardBuilder()
        cancel_kb.add(KeyboardButton(text=context[lang].cancel))
        cancel_kb = cancel_kb.as_markup(resize_keyboard=True)

        # Type episode keyboard
        type_episode_kb = ReplyKeyboardBuilder()
        type_episode_kb.row(
            KeyboardButton(text=context[lang].main_episode),
            KeyboardButton(text=context[lang].episode_aftershow),
        )
        type_episode_kb = type_episode_kb.as_markup(resize_keyboard=True)

        # FTP menu
        ftp_menu_kb = InlineKeyboardBuilder()
        ftp_menu_kb.row(InlineKeyboardButton(text="Загрузить подкаст на FTP", callback_data="FTP_upload"))
        ftp_menu_kb.row(InlineKeyboardButton(text=context[lang].back, callback_data="audio_menu"))
        ftp_menu_kb = ftp_menu_kb.as_markup()

        # WP menu
        wp_menu_kb = InlineKeyboardBuilder()
        wp_menu_kb.row(InlineKeyboardButton(text="Загрузить подкаст на сайт", callback_data="WP_upload"))
        wp_menu_kb.row(InlineKeyboardButton(text=context[lang].back, callback_data="audio_menu"))
        wp_menu_kb = wp_menu_kb.as_markup()

        cache = {
            "cancel": cancel_kb,
            "type_episode": type_episode_kb,
            "audio_menu_main": InlineKeyboardBuilder()
            .add(InlineKeyboardButton(text="FTP", callback_data="FTP_menu"))
            .add(InlineKeyboardButton(text="Сайт", callback_data="WP_menu"))
            .row(InlineKeyboardButton(text="Переслать в чат", callback_data="fwd_verify"))
            .as_markup(),
            "verify": InlineKeyboardBuilder()
            .row(InlineKeyboardButton(text="Подтвердить ✅", callback_data="fwd_verify_yes"))
            .row(InlineKeyboardButton(text="Отмена ❌", callback_data="fwd_verify_no"))
            .as_markup(),
            "audio_menu_post": InlineKeyboardBuilder()
            .add(InlineKeyboardButton(text="FTP", callback_data="FTP_menu"))
            .as_markup(),
            "ftp_menu": ftp_menu_kb,
            "wp_menu": wp_menu_kb,
        }
        _keyboards_cache[lang] = cache
        return cache
    except Exception:
        # Возвращаем пустые клавиатуры, если context не инициализирован
        return {
            "cancel": ReplyKeyboardBuilder().as_markup(),
            "type_episode": ReplyKeyboardBuilder().as_markup(),
            "audio_menu_main": InlineKeyboardBuilder().as_markup(),
            "verify": InlineKeyboardBuilder().as_markup(),
            "audio_menu_post": InlineKeyboardBuilder().as_markup(),
            "ftp_menu": InlineKeyboardBuilder().as_markup(),
            "wp_menu": InlineKeyboardBuilder().as_markup(),
        }


# Функции для получения клавиатур
def get_cancel_kb(lang: str = "ru"):
    return _build_kb_for_lang_podcast(lang)["cancel"]


def get_type_episode_kb(lang: str = "ru"):
    return _build_kb_for_lang_podcast(lang)["type_episode"]


def get_audio_menu_main(lang: str = "ru"):
    return _build_kb_for_lang_podcast(lang)["audio_menu_main"]


def get_verify_kb(lang: str = "ru"):
    return _build_kb_for_lang_podcast(lang)["verify"]


def get_audio_menu_post(lang: str = "ru"):
    return _build_kb_for_lang_podcast(lang)["audio_menu_post"]


def get_ftp_menu(lang: str = "ru"):
    return _build_kb_for_lang_podcast(lang)["ftp_menu"]


def get_wp_menu(lang: str = "ru"):
    return _build_kb_for_lang_podcast(lang)["wp_menu"]
