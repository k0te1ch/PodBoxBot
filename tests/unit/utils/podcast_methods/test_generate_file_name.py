from datetime import datetime
from unittest.mock import patch

import pytest

from utils.podcast_methods import generate_file_name


# Тест для функции
@pytest.mark.parametrize(
    "number, type_episode, current_date, expected",
    [
        ("1", "main", "29112024", "0001_rz_29112024.mp3"),
        ("123", "main", "01122024", "0123_rz_01122024.mp3"),
        ("45", "postshow", "15052023", "0045_postshow_15052023.mp3"),
        ("9999", "postshow", "08082022", "9999_postshow_08082022.mp3"),
        # Алиас "aftershow" (значение из state/UI) должен резолвиться в postshow.
        ("751", "aftershow", "30052026", "0751_postshow_30052026.mp3"),
    ],
)
@patch("utils.podcast_methods.datetime")  # Мокаем datetime.datetime
def test_generate_file_name(mock_datetime, number, type_episode, current_date, expected):
    # Создаем фиксированную дату
    mocked_date = datetime.strptime(current_date, "%d%m%Y")

    # Настраиваем поведение мока
    mock_datetime.now.return_value = mocked_date
    mock_datetime.strptime = datetime.strptime
    mock_datetime.strftime = datetime.strftime

    # Вызываем функцию
    result = generate_file_name(number, type_episode)

    # Проверяем результат
    assert result == expected


def test_generate_file_name_invalid_type_raises():
    """Невалидный type_episode пробрасывает ValueError (а не глотается)."""
    with pytest.raises(ValueError, match="type_episode"):
        generate_file_name("123", "unknown")


def test_generate_file_name_non_str_number_raises():
    with pytest.raises(TypeError, match="number"):
        generate_file_name(123, "main")
