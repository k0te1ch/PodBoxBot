from unittest.mock import patch


@patch("app.utils.wordpress.os.path.exists", return_value=True)
@patch("app.utils.wordpress.pickle.load", return_value={"test_cookie": "test_value"})
@patch("app.utils.wordpress.open", create=True)
def test_load_cookies(mock_open, mock_pickle, mock_exists, wordpress, mock_session):
    mock_open.return_value.__enter__.return_value = mock_open
    result = wordpress._load_cookies()
    assert result
    assert "test_cookie" in mock_session.cookies


from unittest.mock import mock_open, patch


@patch("os.path.exists", return_value=True)
@patch("os.path.getsize", return_value=10)
@patch("builtins.open", new_callable=mock_open)
@patch("pickle.load", return_value={"cookie_name": "cookie_value"})
def test_load_cookies_file_exists_and_has_content(
    mock_pickle_load, mock_open, mock_getsize, mock_exists, wordpress, mock_session
):

    # Выполняем метод _load_cookies
    result = wordpress._load_cookies()

    # Проверяем, что файл открылся и cookies обновлены
    mock_open.assert_called_once_with(wordpress._filename, "rb")
    mock_pickle_load.assert_called_once()
    mock_session.cookies.update.assert_called_once_with({"cookie_name": "cookie_value"})
    assert result is True  # Метод должен вернуть True


@patch("os.path.exists")
@patch("os.path.getsize")
def test_load_cookies_file_does_not_exist(mock_getsize, mock_exists, wordpress):
    mock_exists.return_value = False  # Файл не существует
    mock_getsize.return_value = 0  # Размер не имеет значения, т.к. файл отсутствует

    result = wordpress._load_cookies()

    # Проверяем, что метод вернул False, так как файла нет
    assert result is False


@patch("os.path.exists")
@patch("os.path.getsize")
def test_load_cookies_file_is_empty(mock_getsize, mock_exists, wordpress):
    mock_exists.return_value = True  # Файл существует
    mock_getsize.return_value = 0  # Файл пустой

    result = wordpress._load_cookies()

    # Проверяем, что метод вернул False, так как файл пустой
    assert result is False
