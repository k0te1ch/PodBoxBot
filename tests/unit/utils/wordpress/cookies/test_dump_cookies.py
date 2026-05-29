from unittest.mock import patch

import pytest


@patch("app.utils.wordpress.pickle.dump")
@patch("app.utils.wordpress.open", create=True)
def test_dump_cookies_success(mock_open, mock_pickle, wordpress, mock_session):
    """Тест на успешное сохранение куков"""
    wordpress._filename = "test_cookies.pkl"
    mock_session.cookies = {"test_cookie": "value"}

    mock_open.return_value.__enter__.return_value = mock_open

    result = wordpress._dump_cookies()

    assert result, "Метод _dump_cookies должен возвращать True при успешном сохранении"
    mock_pickle.assert_called_once_with(mock_session.cookies, mock_open)


@patch("app.utils.wordpress.pickle.dump", side_effect=Exception("Ошибка сохранения"))
@patch("app.utils.wordpress.open", create=True)
def test_dump_cookies_fail(mock_open, mock_pickle, wordpress, mock_session):
    """Тест на ошибку при попытке сохранить куки"""

    wordpress._filename = "test_cookies.pkl"

    mock_session.cookies = {"test_cookie": "value"}

    mock_open.return_value.__enter__.return_value = mock_open

    # Проверка на случай возникновения ошибки
    result = wordpress._dump_cookies()

    assert not result, "Метод _dump_cookies должен возвращать False при ошибке сохранения"
    mock_pickle.assert_called_once()


@patch("app.utils.wordpress.pickle.dump")
@patch("app.utils.wordpress.open", create=True)
def test_dump_cookies_no_cookies(mock_open, mock_pickle, wordpress, mock_session):
    """Тест на случай, когда в сессии нет куков для сохранения"""

    wordpress._filename = "test_cookies.pkl"

    mock_session.cookies = {}

    mock_open.return_value.__enter__.return_value = mock_open

    result = wordpress._dump_cookies()

    assert result, "Метод _dump_cookies должен возвращать True даже при отсутствии куков"
    mock_pickle.assert_called_once_with(mock_session.cookies, mock_open)


@patch("app.utils.wordpress.pickle.dump")
@patch("app.utils.wordpress.open", create=True)
def test_dump_cookies_empty_filename(mock_open, mock_pickle, wordpress, mock_session):
    """Тест на случай отсутствия имени файла для сохранения"""

    wordpress._filename = ""  # Пустое имя файла

    mock_session.cookies = {"test_cookie": "value"}

    mock_open.return_value.__enter__.return_value = mock_open

    # Проверка выполнения метода при пустом имени файла
    with pytest.raises(ValueError, match="Имя файла не может быть пустым"):
        wordpress._dump_cookies()
    mock_pickle.assert_not_called()
