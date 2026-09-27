"""Тексты бота из ``locales/*.ftl``.

Один переводчик на всё: его берут меню SDK, резолвер диалога загрузки и
хендлеры. Подстановки передаются явно, именованными аргументами.
"""

from pathlib import Path
from typing import Any

from sagenza_tgbot_sdk.menus import FtlTranslator

LOCALES_DIR = Path(__file__).parent.parent / "locales"
DEFAULT_LOCALE = "ru"

translator = FtlTranslator.from_dir(LOCALES_DIR)


def t(key: str, locale: str = DEFAULT_LOCALE, **params: Any) -> str:
    """Текст по ключу; нет в *locale* — берётся русский, нет и там — сам ключ."""
    for loc in (locale, DEFAULT_LOCALE):
        text = translator(key, loc, **params)
        if text is not None:
            return text
    return key
