"""Тексты бота: как они написаны, а не что в них сказано."""

import pytest
from sagenza_tgbot_sdk.menus import parse_ftl

from services.i18n import LOCALES_DIR

LOCALES = sorted(path.stem for path in LOCALES_DIR.glob("*.ftl"))


def _entries(locale: str) -> dict[str, str]:
    return parse_ftl((LOCALES_DIR / f"{locale}.ftl").read_text(encoding="utf-8"))


def test_both_locales_are_there():
    assert LOCALES == ["en", "ru"]


@pytest.mark.parametrize("locale", LOCALES)
def test_no_message_ends_with_a_period(locale):
    """Бот пишет как человек в мессенджере: без точки в конце сообщения.

    Точки между предложениями внутри текста остаются, многоточие тоже.
    """
    ending = {
        key: value
        for key, value in _entries(locale).items()
        if value.rstrip().endswith(".") and not value.rstrip().endswith("..")
    }

    assert not ending, f"{locale}.ftl: точка в конце у {sorted(ending)}"


def test_locales_have_the_same_keys():
    ru, en = set(_entries("ru")), set(_entries("en"))

    assert ru - en == set(), "нет в en.ftl"
    assert en - ru == set(), "нет в ru.ftl"
