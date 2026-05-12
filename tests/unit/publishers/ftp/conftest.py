import pytest


@pytest.fixture
def sample_upload_event_dict():
    return {
        "event_type": "request",
        "file_name": "rz-123.mp3",
        "path": "/app/files/rz-123.mp3",
        "username": "testuser",
        "metadata": None,
        "bytes_uploaded": 0,
        "total_bytes": 0,
        "progress": 0.0,
        "transfer_speed": 0.0,
        "status": "pending",
        "message_id": "111",
        "chat_id": "222",
    }
