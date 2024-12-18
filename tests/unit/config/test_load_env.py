import pytest
from unittest.mock import patch, MagicMock
import os
from pathlib import Path
from app.config import load_env


@pytest.fixture
def mock_load_dotenv():
    with patch("app.config.load_dotenv") as mock_dotenv:
        yield mock_dotenv


@pytest.fixture
def mock_os_environ_clear():
    with patch("os.environ.clear") as mock_clear:
        yield mock_clear


@pytest.fixture
def mock_getenv():
    with patch("os.getenv") as mock_get:
        yield mock_get


def test_load_env_default(mock_getenv, mock_load_dotenv, mock_os_environ_clear):
    # Настройка: mock getenv, чтобы вернуть ".env" по умолчанию
    mock_getenv.return_value = ".env"

    # Вызываем функцию
    load_env()

    # Проверяем, что os.environ.clear() был вызван
    mock_os_environ_clear.assert_called_once()

    # Проверяем, что load_dotenv был вызван с правильным путем
    expected_path = str(Path.cwd() / ".env")
    mock_load_dotenv.assert_called_once_with(dotenv_path=expected_path, override=True)


def test_load_env_custom_envfile(mock_getenv, mock_load_dotenv, mock_os_environ_clear):
    # Настройка: mock getenv, чтобы вернуть имя другого файла
    mock_getenv.return_value = "custom.env"

    # Вызываем функцию
    load_env()

    # Проверяем, что os.environ.clear() был вызван
    mock_os_environ_clear.assert_called_once()

    # Проверяем, что load_dotenv был вызван с правильным путем
    expected_path = str(Path.cwd() / "custom.env")
    mock_load_dotenv.assert_called_once_with(dotenv_path=expected_path, override=True)


def test_load_env_no_envfile(mock_getenv, mock_load_dotenv, mock_os_environ_clear):
    # Настройка: mock getenv, чтобы вернуть значение, не заканчивающееся на ".env"
    mock_getenv.return_value = "somefile.txt"

    # Вызываем функцию
    load_env()

    # Проверяем, что load_dotenv не был вызван
    mock_load_dotenv.assert_not_called()

    # Проверяем, что os.environ.clear() не был вызван
    mock_os_environ_clear.assert_not_called()
