from aiogram.types import InlineKeyboardButton, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from services import context


def _build(lang: str):
    _cancel = ReplyKeyboardBuilder()
    _cancel.add(KeyboardButton(text=context[lang].cancel))

    _type_episode = ReplyKeyboardBuilder()
    _type_episode.row(
        KeyboardButton(text=context[lang].main_episode),
        KeyboardButton(text=context[lang].episode_aftershow),
    )

    _ftp_menu = InlineKeyboardBuilder()
    _ftp_menu.row(InlineKeyboardButton(text="Загрузить подкаст на FTP", callback_data="FTP_upload"))
    _ftp_menu.row(InlineKeyboardButton(text=context[lang].back, callback_data="audio_menu"))

    _wp_menu = InlineKeyboardBuilder()
    _wp_menu.row(InlineKeyboardButton(text="Загрузить подкаст на сайт", callback_data="WP_upload"))
    _wp_menu.row(InlineKeyboardButton(text=context[lang].back, callback_data="audio_menu"))

    class _Lang:
        cancel = _cancel.as_markup(resize_keyboard=True)
        type_episode = _type_episode.as_markup(resize_keyboard=True)
        audio_menu_main = (
            InlineKeyboardBuilder()
            .add(InlineKeyboardButton(text="FTP", callback_data="FTP_menu"))
            .add(InlineKeyboardButton(text="Сайт", callback_data="WP_menu"))
            .row(InlineKeyboardButton(text="Переслать в чат", callback_data="fwd_verify"))
            .as_markup()
        )
        verify = (
            InlineKeyboardBuilder()
            .row(InlineKeyboardButton(text="Подтвердить ✅", callback_data="fwd_verify_yes"))
            .row(InlineKeyboardButton(text="Отмена ❌", callback_data="fwd_verify_no"))
            .as_markup()
        )
        audio_menu_post = (
            InlineKeyboardBuilder()
            .add(InlineKeyboardButton(text="FTP", callback_data="FTP_menu"))
            .as_markup()
        )
        FTP_menu = _ftp_menu.as_markup()
        WP_menu = _wp_menu.as_markup()

    return _Lang


ru = _build("ru")
en = _build("en")
