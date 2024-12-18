import os
from unittest.mock import patch
import pytest
from config import get_env_value

@pytest.mark.parametrize(
    "env_name, env_value, default, value_type, expected",
    [
        # Преобразование в str (по умолчанию)
        ("MY_STR_VAR", "some_value", "default_value", str, "some_value"),
        ("MY_STR_VAR", None, "default_value", str, "default_value"),
        ("MY_STR_VAR", "none", "default_value", str, "default_value"),
        ("MY_STR_VAR", "", "default_value", str, "default_value"),
        # Преобразование в int
        ("MY_INT_VAR", "42", 0, int, 42),
        ("MY_INT_VAR", "invalid", 0, int, 0),
        ("MY_INT_VAR", None, 5, int, 5),
        # Преобразование в bool
        ("MY_BOOL_VAR", "true", False, bool, True),
        ("MY_BOOL_VAR", "false", True, bool, False),
        ("MY_BOOL_VAR", "1", False, bool, True),
        ("MY_BOOL_VAR", "0", True, bool, False),
        ("MY_BOOL_VAR", "invalid", False, bool, False),
        ("MY_BOOL_VAR", None, True, bool, True),
        # Преобразование в float
        ("MY_FLOAT_VAR", "42.42", 0.0, float, 42.42),
        ("MY_FLOAT_VAR", "invalid", 0.0, float, 0.0),
        ("MY_FLOAT_VAR", None, 5.5, float, 5.5),
        # Преобразование в None
        ("MY_NONE_VAR", "none", "default_value", str, "default_value"),
        ("MY_NONE_VAR", "NONE", "default_value", str, "default_value"),
        ("MY_NONE_VAR", None, "default_value", str, "default_value"),
    ],
)
def test_get_env_value(env_name, env_value, default, value_type, expected):
    """
    Тестирует функцию get_env_value с различными значениями переменных окружения.
    """
    with patch.dict(os.environ, {env_name: env_value} if env_value is not None else {}):
        result = get_env_value(env_name, default, value_type)
        assert result == expected


def test_get_env_value_with_missing_var():
    """
    Тестирует поведение get_env_value при отсутствии переменной окружения.
    """
    with patch.dict(os.environ, {}, clear=True):  # Очищаем окружение
        assert get_env_value("MISSING_VAR", "default_value", str) == "default_value"
        assert get_env_value("MISSING_VAR", 42, int) == 42
        assert get_env_value("MISSING_VAR", 0.0, float) == 0.0
        assert get_env_value("MISSING_VAR", False, bool) == False


def test_get_env_value_with_invalid_type():
    """
    Тестирует поведение get_env_value при недопустимом преобразовании типа.
    """
    with patch.dict(os.environ, {"MY_VAR": "invalid_value"}):
        assert get_env_value("MY_VAR", 0, int) == 0
        assert get_env_value("MY_VAR", False, bool) == False
        assert get_env_value("MY_VAR", 0.0, float) == 0.0
        assert get_env_value("MY_VAR", "default", str) == "invalid_value"
