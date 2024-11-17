import pytest
from unittest.mock import patch
from app.utils.wordpress import WordPress
from collections import UserDict

import pytest
from unittest.mock import patch, MagicMock
from app.utils.wordpress import WordPress


class TrackingDict(UserDict):
    def update(self, *args, **kwargs):
        # Здесь можно добавить логирование или другое отслеживание
        super().update(*args, **kwargs)


@pytest.fixture
def mock_session():
    with patch("app.utils.wordpress.requests.Session", new_callable=MagicMock) as MockSession:
        session_instance = MockSession.return_value
        session_instance.post = MagicMock()
        session_instance.get = MagicMock()

        # Используем TrackingDict вместо обычного словаря
        cookies = TrackingDict()
        cookies.update = MagicMock(wraps=cookies.update)  # отслеживаем вызовы update
        session_instance.cookies = cookies
        yield session_instance


@pytest.fixture
def wordpress(mock_session):
    with patch.object(WordPress, "__init__", lambda self: None):
        wordpress_instance = WordPress()
        wordpress_instance._session = mock_session
        yield wordpress_instance
