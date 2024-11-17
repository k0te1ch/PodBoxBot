def test_close_session(mock_session, wordpress):
    """Тестирует метод close для корректного завершения сессии."""
    # Вызываем метод close() и проверяем, что он корректно закрывает сессию
    wordpress.close()

    # Проверяем, что метод close у mock_session был вызван ровно один раз
    mock_session.close.assert_called_once(), "Метод close() не был вызван один раз на сессии."
