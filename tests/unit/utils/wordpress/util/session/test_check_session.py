from config import WP_URL


def test_check_session_active(mock_session, wordpress):
    """Тест для активной сессии."""
    # Настраиваем mock для возвращения текста, указывающего на активную сессию
    mock_session.get.return_value.text = "wp-admin"

    # Проверяем, что метод _check_session() возвращает True при активной сессии
    assert wordpress._check_session(), "Сессия должна быть активной, но тест этого не подтверждает."


def test_check_session_inactive(mock_session, wordpress):
    """Тест для неактивной сессии."""
    # Настраиваем mock для возвращения текста, указывающего на перенаправление на страницу входа
    mock_session.get.return_value.text = (
        f'document.location.href="{WP_URL.replace("https", "http")}/wp-login.php?redirect_to='
    )

    # Проверяем, что метод _check_session() возвращает False при неактивной сессии
    assert not wordpress._check_session(), "Сессия должна быть неактивной, но тест этого не подтверждает."
