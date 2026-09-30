import sys
from pathlib import Path

import pytest

# Sponsr/main.py импортирует ``sponsr_client`` без пакета — как в контейнере, где
# сервис запускается из /app. Здесь каталог сервиса добавляется в путь.
_SRC = Path(__file__).resolve().parents[4] / "app" / "publishers" / "Sponsr"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture
def event_dict():
    return {
        "event_type": "request",
        "username": "admin",
        "status": "pending",
        "chat_id": "1",
        "message_id": "2",
        "path": "/app/files/0042_postshow.mp3",
        "number": "42",
        "title": "42. Послешоу",
        "comment": "Описание",
        "chapters": [["00:00", "Начало"]],
        "tags": [],
        "type_episode": "aftershow",
    }
