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
