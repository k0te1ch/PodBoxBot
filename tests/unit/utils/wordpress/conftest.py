import pytest
from app.utils.wordpress import WordPress
from collections import UserDict
from unittest.mock import patch, MagicMock


class TrackingDict(UserDict):
    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)


@pytest.fixture(autouse=True)
def mock_session():
    with patch("app.utils.wordpress.requests.Session", new_callable=MagicMock) as MockSession:
        session_instance = MockSession.return_value
        session_instance.post = MagicMock()
        session_instance.get = MagicMock()

        cookies = TrackingDict()
        cookies.update = MagicMock(wraps=cookies.update)
        session_instance.cookies = cookies
        session_instance.headers = {}
        yield session_instance


@pytest.fixture
def wordpress(mock_session):
    with patch.object(WordPress, "__init__", lambda self: None):
        WordPress._instance = None
        wordpress_instance = WordPress()
        wordpress_instance._session = mock_session
        yield wordpress_instance
