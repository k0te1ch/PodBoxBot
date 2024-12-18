import os
from unittest.mock import patch
import pytest
from config import get_env_bool

@pytest.mark.parametrize(
    "env_name, env_value, default, expected",
    [
        # Корректные значения для true
        ("DEBUG", "true", False, True),
        ("DEBUG", "1", False, True),
        ("DEBUG", "TRUE", False, True),
        # Корректные значения для false
        ("DEBUG", "false", True, False),
        ("DEBUG", "0", True, False),
        ("DEBUG", "FALSE", True, False),
        # Некорректные значения
        ("DEBUG", "invalid", False, False),
        ("DEBUG", "", True, True),
        ("DEBUG", None, False, False),
    ],
)
def test_get_env_bool(env_name, env_value, default, expected):
    """
    Тестирует функцию get_env_bool с различными значениями переменных окружения.
    """
    with patch.dict(os.environ, {env_name: env_value} if env_value is not None else {}):
        assert get_env_bool(env_name, default) == expected


def test_get_env_bool_missing_env_variable():
    """
    Тестирует поведение get_env_bool при отсутствии переменной окружения.
    """
    with patch.dict(os.environ, {}, clear=True):  # Очищаем окружение
        assert get_env_bool("MISSING_VAR", default=True) == True
        assert get_env_bool("MISSING_VAR", default=False) == False
