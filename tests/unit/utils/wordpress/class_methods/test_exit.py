import pytest
from unittest.mock import patch

from app.utils.wordpress import WordPress


@patch.object(WordPress, "close")
def test_exit_method_calls_close(mock_close):
    wp = WordPress()
    with wp:
        pass
    # Проверяем, что метод close был вызван при выходе из контекста
    mock_close.assert_called_once()


@patch.object(WordPress, "close")
def test_exit_method_without_exception(mock_close):
    wp = WordPress()
    with wp:
        pass
    # Проверяем, что close вызывается при отсутствии исключения
    mock_close.assert_called_once()


@patch.object(WordPress, "close")
def test_exit_method_with_exception(mock_close):
    wp = WordPress()
    with pytest.raises(ValueError):
        with wp:
            raise ValueError("Test exception")
    # Проверяем, что close вызывается, даже если произошло исключение
    mock_close.assert_called_once()
