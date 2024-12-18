import pytest
from app.config import parse_bool


@pytest.mark.parametrize(
    "value, default, expected",
    [
        # Корректные строки для true
        ("true", False, True),
        ("TRUE", False, True),
        ("1", False, True),
        ("  true  ", False, True),
        (" 1 ", False, True),
        # Корректные строки для false
        ("false", True, False),
        ("FALSE", True, False),
        ("0", True, False),
        ("  false  ", True, False),
        (" 0 ", True, False),
        # Некорректные значения
        ("invalid", True, True),
        ("", False, False),
        (None, True, True),
        (123, False, False),
        ([False], True, True),
    ],
)
def test_parse_bool(value, default, expected):
    """
    Тест для функции parse_bool.
    """
    assert parse_bool(value, default) == expected
