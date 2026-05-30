"""Tests for the WordPress publisher client."""

import pickle
from unittest.mock import MagicMock, patch

import pytest
import pytz
from app.publishers.WordPress.wordpress import WordPress
from requests.auth import HTTPBasicAuth


class TestWordPressInit:
    @patch("app.publishers.WordPress.wordpress.requests.Session")
    @patch("app.publishers.WordPress.wordpress.os.path.exists", return_value=False)
    @patch("app.publishers.WordPress.wordpress.UserAgent")
    def test_creates_session_on_init(self, mock_ua, mock_exists, mock_session_cls):
        mock_ua.return_value.random = "TestAgent/1.0"
        session_instance = mock_session_cls.return_value
        # All HTTP now flows through Session.request(); a string body keeps the
        # bot-protection regex happy and a 200 makes the bootstrap _login() bail
        # out cleanly without raising.
        session_instance.request.return_value = MagicMock(status_code=200, text="")

        wp = WordPress("https://example.com", "user", "pass", "app-pass", "/tmp/cookie.pkl")
        assert wp._wp_url == "https://example.com"
        assert wp._session is not None

    @patch("app.publishers.WordPress.wordpress.requests.Session")
    @patch("app.publishers.WordPress.wordpress.os.path.exists", return_value=False)
    @patch("app.publishers.WordPress.wordpress.UserAgent")
    def test_strips_trailing_slash(self, mock_ua, mock_exists, mock_session_cls):
        mock_ua.return_value.random = "TestAgent/1.0"
        session_instance = mock_session_cls.return_value
        session_instance.request.return_value = MagicMock(status_code=200, text="")

        wp = WordPress("https://example.com/", "user", "pass", "app-pass", "/tmp/cookie.pkl")
        assert wp._wp_url == "https://example.com"


class TestWordPressCookies:
    def test_dump_cookies(self, mock_session, tmp_path):
        cookie_path = str(tmp_path / "cookie.pkl")

        wp = WordPress.__new__(WordPress)
        wp._session = mock_session
        wp._cookie_path = cookie_path
        wp._session.cookies = {"test": "value"}

        result = wp._dump_cookies()
        assert result is True

        with open(cookie_path, "rb") as f:
            loaded = pickle.load(f)
        assert loaded == {"test": "value"}

    def test_dump_cookies_empty_path_raises(self, mock_session):
        wp = WordPress.__new__(WordPress)
        wp._session = mock_session
        wp._cookie_path = ""

        with pytest.raises(ValueError, match="Cookie path cannot be empty"):
            wp._dump_cookies()

    def test_load_cookies_file_exists(self, mock_session, tmp_path):
        cookie_path = str(tmp_path / "cookie.pkl")
        with open(cookie_path, "wb") as f:
            pickle.dump({"loaded": "cookie"}, f)

        wp = WordPress.__new__(WordPress)
        wp._session = mock_session
        wp._cookie_path = cookie_path

        result = wp._load_cookies()
        assert result is True
        mock_session.cookies.update.assert_called_once()

    def test_load_cookies_no_file(self, mock_session, tmp_path):
        wp = WordPress.__new__(WordPress)
        wp._session = mock_session
        wp._cookie_path = str(tmp_path / "nonexistent.pkl")

        result = wp._load_cookies()
        assert result is False


def _make_wp(mock_session, *, timezone="Europe/Moscow"):
    """A WordPress instance wired for upload_post tests.

    Bypasses __init__ (no real HTTP on construction) and stubs the REST side:
    upload_post now reserves a Podlove episode and pushes metadata/chapters via
    the Application-Password REST session, so a working _app_auth + _rest_session
    are required for the happy path.
    """
    wp = WordPress.__new__(WordPress)
    wp._session = mock_session
    wp._wp_url = "https://example.com"
    wp._wp_login = "user"
    wp._wp_password = "pass"
    wp._cookie_path = "/tmp/test.pkl"
    wp._timezone = pytz.timezone(timezone)
    wp._app_auth = HTTPBasicAuth("user", "app-pass")
    rest_session = MagicMock()
    rest_session.request.return_value = MagicMock(ok=True, status_code=200, text="{}")
    wp._rest_session = rest_session
    return wp


_FORM_PAGE = b"""
<html><body>
<form name="post">
    <input type="hidden" name="_wpnonce" value="abc123"/>
    <input type="hidden" name="post_ID" value="99"/>
</form>
<script>var podlove_vue = {"post_id": 99, "episode_id": 42};</script>
</body></html>
"""


class TestWordPressUploadPost:
    def test_upload_post_success(self, mock_session, sample_post_info):
        get_resp = MagicMock(status_code=200, ok=True, content=_FORM_PAGE, text=_FORM_PAGE.decode())
        post_resp = MagicMock(status_code=302, ok=True, text="")

        def _request(method, url, **kwargs):
            return post_resp if method == "POST" else get_resp

        mock_session.request.side_effect = _request

        wp = _make_wp(mock_session)

        with patch.object(wp, "_dump_cookies", return_value=True):
            result = wp.upload_post(sample_post_info)

        assert result is True
        # The post got submitted and Podlove metadata pushed over REST.
        mock_session.request.assert_called()
        wp._rest_session.request.assert_called()

    def test_upload_post_no_form_retries_login(self, mock_session, sample_post_info):
        empty_page = b"<html><body>No form here</body></html>"
        get_calls = {"n": 0}

        def _request(method, url, **kwargs):
            if method == "POST":
                return MagicMock(status_code=302, ok=True, text="")
            get_calls["n"] += 1
            content = empty_page if get_calls["n"] == 1 else _FORM_PAGE
            return MagicMock(status_code=200, ok=True, content=content, text=content.decode())

        mock_session.request.side_effect = _request

        wp = _make_wp(mock_session, timezone="UTC")

        with (
            patch.object(wp, "_dump_cookies", return_value=True),
            patch.object(wp, "_login", return_value=True) as mock_login,
        ):
            result = wp.upload_post(sample_post_info)

        assert result is True
        mock_login.assert_called_once()


class TestWordPressContextManager:
    def test_enter_returns_self(self, mock_session):
        wp = WordPress.__new__(WordPress)
        wp._session = mock_session
        assert wp.__enter__() is wp

    def test_exit_closes_session(self, mock_session):
        wp = WordPress.__new__(WordPress)
        wp._session = mock_session
        wp._rest_session = MagicMock()
        wp.__exit__(None, None, None)
        mock_session.close.assert_called_once()
        wp._rest_session.close.assert_called_once()
