def test_upload_post(mock_session, caplog, wordpress):
    info = {
        "number": "1",
        "title": "Test Title",
        "comment": "Test Comment",
        "chapters": [("00:00", "Intro")],
        "slug": "test-slug",
        "duration": "00:30",
        "tags": ["test", "post"],
    }

    # Настройка mock-ответов для запросов
    mock_session.get.return_value.content = b"<html><form name='post'></form></html>"
    mock_session.post.return_value.status_code = 200

    # Выполнение метода upload_post
    with caplog.at_level("DEBUG"):
        wordpress.upload_post(info)

    # Проверка наличия определенного сообщения в логах
    assert any("Starting post upload process" in record.message for record in caplog.records), (
        "Сообщение 'Starting post upload process' должно быть залогировано"
    )

    # Проверка вызова post запроса
    mock_session.post.assert_called()


def test_upload_post_hidden_fields(mock_session, wordpress):
    # Предопределяем HTML-структуру с формой, содержащей скрытые поля
    html_content = """
    <form name="post">
        <input type="hidden" name="hidden_field_1" value="hidden_value_1"/>
        <input type="hidden" name="hidden_field_2" value="hidden_value_2"/>
    </form>
    """

    # Замокированный ответ от `self._session.get`
    mock_session.get.return_value.content = html_content.encode("utf-8")

    # Тестируемые данные для загрузки
    info = {
        "number": "123",
        "title": "Test Title",
        "comment": "Test Summary",
        "chapters": [("00:00", "Intro")],
        "slug": "test-slug",
        "duration": "10:00",
        "tags": ["tag1", "tag2"],
    }

    # Выполняем функцию `upload_post`
    wordpress.upload_post(info)

    # Проверяем, что скрытые поля добавлены
    assert "hidden_field_1" in mock_session.post.call_args[1]["data"]
    assert mock_session.post.call_args[1]["data"]["hidden_field_1"] == "hidden_value_1"
    assert "hidden_field_2" in mock_session.post.call_args[1]["data"]
    assert mock_session.post.call_args[1]["data"]["hidden_field_2"] == "hidden_value_2"
