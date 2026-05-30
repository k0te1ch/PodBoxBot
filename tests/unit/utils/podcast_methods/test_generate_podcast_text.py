from unittest.mock import patch

import pytest

from utils.podcast_methods import generate_podcast_text


@pytest.fixture
def podcast_info():
    """Фикстура с данными для тестирования."""
    return {
        "number": "42",
        "title": "Название эпизода",
        "comment": "Это описание эпизода.",
        "chapters": [
            ["00:00:07", "Вступление"],
            ["00:10:20", "Основная часть"],
            ["00:40:15", "Заключение"],
        ],
        "support_link": "https://support.link",
    }


@patch("utils.podcast_methods.SUPPORT_LINK", "https://support.link")
def test_generate_podcast_text(podcast_info):
    """Тестирует генерацию текста для подкаста."""
    expected_output = (
        "<b>Название эпизода</b>\n\n"
        "<i>Описание:</i>\n"
        "Это описание эпизода.\n\n"
        "<i>Таймлайн:</i>\n"
        "00:00:07 — Вступление\n"
        "00:10:20 — Основная часть\n"
        "00:40:15 — Заключение\n\n"
        "Всё это вы услышите в 42-м эпизоде подкаста «Разговорный жанр».\n\n"
        '<i><b><a href="https://support.link">🍩 Поддержать подкаст</a></b></i>'
    )

    result = generate_podcast_text(podcast_info)
    assert result == expected_output
