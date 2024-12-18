import os
from unittest.mock import patch
import pytest
from config import get_env_str


@pytest.mark.parametrize(
    "env_name, env_value, default, required, expected, raises_exception",
    [
        # Тесты с дефолтными значениями
        ("MY_VAR", "some_value", None, False, "some_value", False),
        ("MY_VAR", "none", None, False, None, False),
        ("MY_VAR", "", "default_value", False, "default_value", False),
        ("MY_VAR", "none", "default_value", False, "default_value", False),
        ("MY_VAR", "some_value", "default_value", False, "some_value", False),
        # Тесты с обязательными значениями
        ("MY_VAR", "some_value", None, True, "some_value", False),
        ("MY_VAR", "none", None, True, None, True),
        ("MY_VAR", None, "default_value", False, "default_value", False),
        ("MY_VAR", None, None, True, None, True),  # Ожидаем исключение
        # Тесты с отсутствующей переменной окружения
        ("MISSING_VAR", None, "default_value", False, "default_value", False),
        ("MISSING_VAR", None, None, True, None, True),  # Ожидаем исключение
    ],
)
def test_get_env_str(env_name, env_value, default, required, expected, raises_exception):
    """
    Тестирует функцию get_env_str с различными значениями переменных окружения.
    """
    with patch.dict(os.environ, {env_name: env_value} if env_value is not None else {}):
        if raises_exception:
            with pytest.raises(NameError, match=f'name "{env_name}" is not defined in your env file'):
                get_env_str(env_name, default, required)
        else:
            assert get_env_str(env_name, default, required) == expected
