import sys
from pathlib import Path

import pytest

# Boosty/main.py uses bare ``from boosty_client import ...`` (and boosty_client
# imports ``from content import ...``) — those resolve in-container because
# main.py runs from /app with the service sources alongside it. Outside the
# container that dir isn't on the path, so add it here (mirrors WordPress).
_BOOSTY_SRC = Path(__file__).resolve().parents[4] / "app" / "publishers" / "Boosty"
if str(_BOOSTY_SRC) not in sys.path:
    sys.path.insert(0, str(_BOOSTY_SRC))


@pytest.fixture
def sample_boosty_post_info():
    return {
        "number": "123",
        "title": "123. Тестовый эпизод",
        "comment": "Описание тестового эпизода.\nВторой абзац.",
        "chapters": [["00:00:00", "Начало"], ["00:10:00", "Середина"]],
        "tags": ["тест", "подкаст"],
    }


@pytest.fixture
def sample_boosty_event_dict(sample_boosty_post_info):
    return {
        "event_type": "request",
        "username": "testuser",
        "status": "pending",
        "chat_id": "12345",
        "message_id": "67890",
        "path": "/app/files/0123_postshow.mp3",
        "type_episode": "aftershow",
        **sample_boosty_post_info,
    }
