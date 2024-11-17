from unittest.mock import patch, Mock

from config import WP_URL


@patch("app.utils.wordpress.WordPress._dump_cookies", return_value=True)
def test_login_success(mock_dump_cookies, wordpress, mock_session):
    """Тест на успешный логин, когда метод возвращает True"""

    # Настраиваем mock для первого запроса
    mock_response_first = Mock()
    mock_response_first.status_code = 200
    mock_response_first.text = (
        f'document.cookie="wordpress_logged_in=some_value; path=/";'
        f'document.location.href="{WP_URL.replace("https", "http")}/wp-login.php"'
    )

    # Настраиваем mock для второго запроса
    mock_response_second = Mock()
    mock_response_second.status_code = 200
    mock_response_second.text = f'document.location.href="{WP_URL.replace("https", "http")}/wp-admin"'

    # Указываем возвращаемые значения для двух вызовов `post`
    mock_session.post.side_effect = [mock_response_first, mock_response_second]

    assert wordpress._login(), "Логин должен быть успешным, но метод вернул False"
    mock_dump_cookies.assert_called_once()


@patch("app.utils.wordpress.WordPress._dump_cookies", return_value=True)
def test_login_failed_status_code(mock_dump_cookies, wordpress, mock_session):
    """Тест на неудачный логин из-за неверного статус-кода"""
    mock_response = Mock()
    mock_response.status_code = 403  # Например, доступ запрещен
    mock_session.post.return_value = mock_response

    result = wordpress._login()
    assert not result, "Метод должен возвращать False при неуспешном статусе входа"
    mock_dump_cookies.assert_not_called()


@patch("app.utils.wordpress.WordPress._dump_cookies", return_value=False)
def test_login_failed_redirect(mock_dump_cookies, wordpress, mock_session):
    """Тест на неудачный логин из-за отсутствия перенаправления на страницу входа"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "Some other text without redirect"
    mock_session.post.return_value = mock_response

    assert not wordpress._login(), "Метод должен возвращать False при отсутствии перенаправления на логин."
    mock_dump_cookies.assert_not_called()


@patch("app.utils.wordpress.WordPress._dump_cookies", return_value=True)
def test_login_cookie_setting(mock_dump_cookies, wordpress, mock_session):
    """Тест на установку куки при успешном логине"""

    # Настраиваем mock для первого запроса
    mock_response_first = Mock()
    mock_response_first.status_code = 200
    mock_response_first.text = (
        f'document.cookie="wordpress_logged_in=some_value; path=/";'
        f'document.location.href="{WP_URL.replace("https", "http")}/wp-login.php"'
    )

    # Настраиваем mock для второго запроса
    mock_response_second = Mock()
    mock_response_second.status_code = 200
    mock_response_second.text = f'document.location.href="{WP_URL.replace("https", "http")}/wp-admin"'

    # Указываем side_effect для обработки двух вызовов `post`
    mock_session.post.side_effect = [mock_response_first, mock_response_second]

    wordpress._login()

    # Проверяем, что куки 'wordpress_logged_in' добавлен
    assert "wordpress_logged_in" in mock_session.cookies, "Cookie wordpress_logged_in не установлен."
    assert (
        mock_session.cookies["wordpress_logged_in"] == "some_value"
    ), "Неверное значение для куки wordpress_logged_in."

    # Проверка вызова _dump_cookies
    mock_dump_cookies.assert_called_once()


@patch("app.utils.wordpress.WordPress._dump_cookies", return_value=True)
def test_login_multiple_cookie_handling(mock_dump_cookies, wordpress, mock_session):
    """Тест на корректное управление несколькими куками при успешном логине"""

    # Настройка mock для первого ответа с двумя куками
    mock_response_first = Mock()
    mock_response_first.status_code = 200
    mock_response_first.text = (
        'document.cookie="wordpress_logged_in=some_value; path=/";'
        'document.cookie="another_cookie=another_value; path=/";'
        f'document.location.href="{WP_URL.replace("https", "http")}/wp-login.php"'
    )

    # Настройка mock для второго ответа с перенаправлением на wp-admin
    mock_response_second = Mock()
    mock_response_second.status_code = 200
    mock_response_second.text = f'document.location.href="{WP_URL.replace("https", "http")}/wp-admin"'

    # Указываем последовательность ответов для вызовов post
    mock_session.post.side_effect = [mock_response_first, mock_response_second]

    wordpress._login()

    # Проверка наличия и корректности значений куков
    assert "wordpress_logged_in" in mock_session.cookies, "Cookie wordpress_logged_in не установлен."
    assert mock_session.cookies["wordpress_logged_in"] == "some_value", "Неверное значение для wordpress_logged_in."
    assert "another_cookie" in mock_session.cookies, "Cookie another_cookie не установлен."
    assert mock_session.cookies["another_cookie"] == "another_value", "Неверное значение для another_cookie."

    # Проверка вызова _dump_cookies
    mock_dump_cookies.assert_called_once()
