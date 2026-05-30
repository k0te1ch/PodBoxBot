from utils.MP3_methods import time_to_milliseconds


def test_time_to_seconds_valid_input():
    """Тестирование корректного преобразования времени"""
    assert time_to_milliseconds("01:02:03") == 3723000  # (1 час * 3600) + (2 минуты * 60) + 3 секунды
    assert time_to_milliseconds("00:00:00") == 0  # Начальное время
    assert time_to_milliseconds("23:59:59") == 86399000  # Максимум за сутки


def test_time_to_seconds_single_digit():
    """Тестирование времени с одноразрядными значениями"""
    assert time_to_milliseconds("1:2:3") == 3723000  # Ожидаем такое же, как "01:02:03"


def test_time_to_seconds_invalid_format(caplog):
    """Тестирование некорректного формата времени с проверкой логов"""
    with caplog.at_level("ERROR"):
        assert time_to_milliseconds("invalid:format") is None  # Некорректный формат возвращает None
        assert "Invalid time format" in caplog.text  # Проверяем, что сообщение об ошибке было залогировано

    with caplog.at_level("ERROR"):
        assert time_to_milliseconds("25:61:61") is None  # Неправильные значения времени
        assert "Invalid time value" in caplog.text  # Проверяем, что сообщение об ошибке было залогировано


def test_time_to_seconds_partial_input(caplog):
    """Тестирование, когда подано меньше 3 значений с проверкой логов"""
    with caplog.at_level("ERROR"):
        assert time_to_milliseconds("12:34") is None  # Не хватает секунд
        assert "Invalid time format" in caplog.text  # Проверяем, что ошибка была залогирована

    with caplog.at_level("ERROR"):
        assert time_to_milliseconds("12") is None  # Не хватает минут и секунд
        assert "Invalid time format" in caplog.text  # Проверяем, что ошибка была залогирована


def test_time_to_seconds_negative_input(caplog):
    """Тестирование отрицательных значений с проверкой логов"""
    with caplog.at_level("ERROR"):
        assert time_to_milliseconds("-01:00:00") is None  # Отрицательные значения должны возвращать None
        assert "Invalid time value" in caplog.text  # Проверяем, что ошибка была залогирована
