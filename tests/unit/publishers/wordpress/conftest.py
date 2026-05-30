import sys
from collections import UserDict
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# WordPress/main.py uses a bare ``from wordpress import WordPress`` — that
# resolves in-container because main.py runs from /app with wordpress.py
# alongside it. Outside the container the service source dir isn't on the
# path, so add it here (mirrors how the suite injects ``shared`` via app/).
_WP_SRC = Path(__file__).resolve().parents[4] / "app" / "publishers" / "WordPress"
if str(_WP_SRC) not in sys.path:
    sys.path.insert(0, str(_WP_SRC))


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
