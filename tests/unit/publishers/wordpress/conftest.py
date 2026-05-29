from collections import UserDict
from unittest.mock import MagicMock

import pytest


class TrackingDict(UserDict):
    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)


@pytest.fixture
def mock_session():
    session = MagicMock()
    cookies = TrackingDict()
    cookies.update = MagicMock(wraps=cookies.update)
    session.cookies = cookies
    session.headers = {}
    session.post = MagicMock()
    session.get = MagicMock()
    session.close = MagicMock()
    return session


@pytest.fixture
def sample_post_info():
    return {
        "number": "123",
        "title": "123. Тестовый эпизод",
        "comment": "Описание тестового эпизода",
        "chapters": [["00:00:00", "Начало"], ["00:10:00", "Середина"]],
        "tags": ["тест", "подкаст"],
        "slug": "rz-123",
        "duration": 3600,
    }


@pytest.fixture
def sample_wp_event_dict(sample_post_info):
    return {
        "event_type": "request",
        "username": "testuser",
        "status": "pending",
        "chat_id": "12345",
        "message_id": "67890",
        **sample_post_info,
    }
