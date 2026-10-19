"""Tests for the WordPress publisher client."""

import json
from unittest.mock import MagicMock, patch

import pytest
import pytz
from app.publishers.WordPress.wordpress import WordPress
from requests.auth import HTTPBasicAuth
from requests.cookies import RequestsCookieJar
from sagenza_tgbot_sdk.masking import default_masker, mask_secrets


class TestWordPressInit:
    @patch("app.publishers.WordPress.wordpress.requests.Session")
    @patch("app.publishers.WordPress.wp_http.os.path.exists", return_value=False)
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
    @patch("app.publishers.WordPress.wp_http.os.path.exists", return_value=False)
    @patch("app.publishers.WordPress.wordpress.UserAgent")
    def test_strips_trailing_slash(self, mock_ua, mock_exists, mock_session_cls):
        mock_ua.return_value.random = "TestAgent/1.0"
        session_instance = mock_session_cls.return_value
        session_instance.request.return_value = MagicMock(status_code=200, text="")

        wp = WordPress("https://example.com/", "user", "pass", "app-pass", "/tmp/cookie.pkl")
        assert wp._wp_url == "https://example.com"


class TestWordPressCookies:
    def test_dump_cookies_writes_json_with_domain_and_path(self, mock_session, tmp_path):
        cookie_path = str(tmp_path / "cookie.json")
        jar = RequestsCookieJar()
        jar.set("wordpress_logged_in", "abc", domain="example.com", path="/")
        jar.set("bpc", "deadbeef", domain="cdn.example.com", path="/")

        wp = WordPress.__new__(WordPress)
        wp._session = mock_session
        wp._cookie_path = cookie_path
        wp._session.cookies = jar

        assert wp._dump_cookies() is True

        with open(cookie_path, encoding="utf-8") as f:
            written = json.load(f)
        assert {(c["name"], c["value"], c["domain"], c["path"]) for c in written} == {
            ("wordpress_logged_in", "abc", "example.com", "/"),
            ("bpc", "deadbeef", "cdn.example.com", "/"),
        }

    def test_dump_cookies_empty_path_raises(self, mock_session):
        wp = WordPress.__new__(WordPress)
        wp._session = mock_session
        wp._cookie_path = ""

        with pytest.raises(ValueError, match="Cookie path cannot be empty"):
            wp._dump_cookies()

    def test_cookies_survive_a_dump_load_round_trip(self, tmp_path):
        cookie_path = str(tmp_path / "cookie.json")
        source = RequestsCookieJar()
        source.set("wordpress_logged_in", "abc", domain="example.com", path="/")

        writer = WordPress.__new__(WordPress)
        writer._session = MagicMock(cookies=source)
        writer._cookie_path = cookie_path
        assert writer._dump_cookies() is True

        reader = WordPress.__new__(WordPress)
        reader._session = MagicMock(cookies=RequestsCookieJar())
        reader._cookie_path = cookie_path
        assert reader._load_cookies() is True

        restored = reader._session.cookies
        assert restored.get("wordpress_logged_in", domain="example.com", path="/") == "abc"

    def test_load_cookies_no_file(self, mock_session, tmp_path):
        wp = WordPress.__new__(WordPress)
        wp._session = mock_session
        wp._cookie_path = str(tmp_path / "nonexistent.json")

        assert wp._load_cookies() is False

    def test_legacy_pickle_file_is_ignored_not_unpickled(self, tmp_path):
        """A file left by the pickle version must never be deserialized."""
        cookie_path = tmp_path / "cookie.pkl"
        # Начало pickle-протокола: точно не JSON.
        cookie_path.write_bytes(bytes([0x80, 0x04, 0x95]) + b"not-json")

        wp = WordPress.__new__(WordPress)
        wp._session = MagicMock(cookies=RequestsCookieJar())
        wp._cookie_path = str(cookie_path)

        assert wp._load_cookies() is False
        assert len(wp._session.cookies) == 0


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

    def test_upload_post_form_and_rest_payload(self, mock_session, sample_post_info):
        """Регресс на баги черновика: Title = имя эпизода, без <code> и big_post,
        recording_date уходит в Podlove и в тело поста."""
        sample_post_info["recording_date"] = "2026-06-05"

        get_resp = MagicMock(status_code=200, ok=True, content=_FORM_PAGE, text=_FORM_PAGE.decode())
        post_resp = MagicMock(status_code=302, ok=True, text="")
        captured = {}

        def _request(method, url, **kwargs):
            if method == "POST" and url.endswith("/wp-admin/post.php"):
                captured["form"] = kwargs["data"]
                return post_resp
            return get_resp

        mock_session.request.side_effect = _request

        wp = _make_wp(mock_session)
        with patch.object(wp, "_dump_cookies", return_value=True):
            assert wp.upload_post(sample_post_info) is True

        content = captured["form"]["content"]
        # #3 — никаких <code> в теле
        assert "<code>" not in content
        # описание присутствует как обычный текст
        assert sample_post_info["comment"] in content
        # #2 — дата записи из info, а не сегодняшняя
        assert "Дата записи: 5 июня 2026" in content
        # #4 — big_post убран
        assert "metakeyselect" not in captured["form"]
        assert "metavalue" not in captured["form"]

        # #1 + #2 — REST-обновление Podlove: title = имя эпизода, recording_date проброшен
        episode_calls = [c for c in wp._rest_session.request.call_args_list if "/podlove/v2/episodes/" in c.args[1]]
        assert episode_calls, "Podlove episode update not called"
        payload = episode_calls[0].kwargs["json"]
        assert payload["title"] == sample_post_info["title"]
        assert payload["recording_date"] == "2026-06-05"

    def test_post_title_is_restored_after_podlove_overwrites_it(self, mock_session, sample_post_info):
        """Podlove копирует title эпизода в заголовок записи — возвращаем «Разговорный жанр — N»."""
        get_resp = MagicMock(status_code=200, ok=True, content=_FORM_PAGE, text=_FORM_PAGE.decode())
        mock_session.request.side_effect = lambda method, url, **kw: (
            MagicMock(status_code=302, ok=True, text="") if method == "POST" else get_resp
        )
        wp = _make_wp(mock_session)
        with (
            patch.object(wp, "_dump_cookies", return_value=True),
            patch.object(wp, "podcast_rest_path", return_value="/wp/v2/episodes/99"),
        ):
            assert wp.upload_post(sample_post_info) is True

        calls = wp._rest_session.request.call_args_list
        episode_update = next(i for i, c in enumerate(calls) if "/podlove/v2/episodes/" in c.args[1])
        title_restore = [
            i for i, c in enumerate(calls) if c.args[1].endswith("/wp/v2/episodes/99") and "title" in c.kwargs["json"]
        ]
        assert title_restore, "post title was not restored"
        assert title_restore[0] > episode_update
        number = sample_post_info["number"]
        assert calls[title_restore[0]].kwargs["json"] == {"title": f"Разговорный жанр — {number}"}

    def _submitted_form(self, mock_session, info) -> dict:
        get_resp = MagicMock(status_code=200, ok=True, content=_FORM_PAGE, text=_FORM_PAGE.decode())
        post_resp = MagicMock(status_code=302, ok=True, text="")
        captured = {}

        def _request(method, url, **kwargs):
            if method == "POST" and url.endswith("/wp-admin/post.php"):
                captured["form"] = kwargs["data"]
                return post_resp
            return get_resp

        mock_session.request.side_effect = _request
        wp = _make_wp(mock_session)
        with patch.object(wp, "_dump_cookies", return_value=True):
            assert wp.upload_post(info) is True
        return captured["form"]

    def test_chosen_publication_date_goes_into_the_editor_date_fields(self, mock_session, sample_post_info):
        """Дата публикации, выбранная в боте, становится датой записи в черновике."""
        sample_post_info["publish_at"] = "2026-10-05T20:07"

        form = self._submitted_form(mock_session, sample_post_info)

        dated = {name: form[name] for name in ("edit_date", "aa", "mm", "jj", "hh", "mn", "ss")}
        assert dated == {"edit_date": "1", "aa": "2026", "mm": "10", "jj": "05", "hh": "20", "mn": "07", "ss": "00"}

    @pytest.mark.parametrize("publish_at", [None, "", "soon"])
    def test_draft_keeps_the_default_date_without_a_chosen_one(self, mock_session, sample_post_info, publish_at):
        sample_post_info["publish_at"] = publish_at

        form = self._submitted_form(mock_session, sample_post_info)

        assert not {"edit_date", "aa", "mm", "jj", "hh", "mn"} & set(form)

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


def _rest_json(routes: dict):
    """side_effect для _rest_session.request: путь -> JSON-ответ."""

    def _request(method, url, **kwargs):
        for suffix, body in routes.items():
            if url.endswith(suffix):
                return MagicMock(ok=True, status_code=200, text="", json=MagicMock(return_value=body))
        return MagicMock(ok=True, status_code=200, text="{}", json=MagicMock(return_value={}))

    return _request


class TestWordPressIdempotency:
    def test_existing_draft_is_updated_not_duplicated(self, mock_session, sample_post_info):
        urls = []

        def _request(method, url, **kwargs):
            urls.append((method, url))
            if method == "POST":
                return MagicMock(status_code=302, ok=True, text="", url="https://example.com/wp-admin/post.php")
            return MagicMock(status_code=200, ok=True, content=_FORM_PAGE, text=_FORM_PAGE.decode())

        mock_session.request.side_effect = _request
        wp = _make_wp(mock_session)
        wp._rest_session.request.side_effect = _rest_json(
            {
                "/podlove/v2/episodes?status=draft": {
                    "results": [{"id": 7, "title": "Другое"}, {"id": 42, "title": "Разговорный жанр &#8212; 123"}]
                },
                "/podlove/v2/episodes/42": {"id": 42, "post_id": 555},
            }
        )

        with patch.object(wp, "_dump_cookies", return_value=True):
            assert wp.upload_post(sample_post_info) is True

        assert ("GET", "https://example.com/wp-admin/post.php?post=555&action=edit") in urls
        assert not any("post-new.php" in u for _, u in urls)
        assert wp.last_post_id == "555"

    def test_draft_lookup_failure_falls_back_to_new_post(self, mock_session, sample_post_info):
        mock_session.request.side_effect = lambda method, url, **kw: (
            MagicMock(status_code=302, ok=True, text="")
            if method == "POST"
            else MagicMock(status_code=200, ok=True, content=_FORM_PAGE, text=_FORM_PAGE.decode())
        )
        wp = _make_wp(mock_session)
        rest_ok = MagicMock(ok=True, status_code=200, text="{}")
        wp._rest_session.request.side_effect = [MagicMock(ok=False, status_code=500, text="boom"), *[rest_ok] * 4]

        with patch.object(wp, "_dump_cookies", return_value=True):
            assert wp.upload_post(sample_post_info) is True
        assert wp.last_post_id == "99"

    def test_redirect_to_login_on_submit_is_an_error(self, mock_session, sample_post_info):
        mock_session.request.side_effect = lambda method, url, **kw: (
            MagicMock(status_code=200, ok=True, text="login", url="https://example.com/wp-login.php?redirect_to=x")
            if method == "POST"
            else MagicMock(status_code=200, ok=True, content=_FORM_PAGE, text=_FORM_PAGE.decode())
        )
        wp = _make_wp(mock_session)
        with patch.object(wp, "_dump_cookies", return_value=True), pytest.raises(RuntimeError, match="wp-login"):
            wp.upload_post(sample_post_info)

    def test_hidden_input_without_value_does_not_crash(self, mock_session, sample_post_info):
        page = _FORM_PAGE.replace(b"</form>", b'<input type="hidden" name="empty"/><input type="hidden"/></form>')
        captured = {}

        def _request(method, url, **kwargs):
            if method == "POST":
                captured["form"] = kwargs["data"]
                return MagicMock(status_code=302, ok=True, text="")
            return MagicMock(status_code=200, ok=True, content=page, text=page.decode())

        mock_session.request.side_effect = _request
        wp = _make_wp(mock_session)
        with patch.object(wp, "_dump_cookies", return_value=True):
            assert wp.upload_post(sample_post_info) is True
        assert captured["form"]["empty"] == ""


class TestPodcastRestPath:
    def test_uses_rest_base_from_types_endpoint(self, mock_session):
        wp = _make_wp(mock_session)
        wp._rest_session.request.side_effect = _rest_json({"/wp/v2/types/podcast": {"rest_base": "episodes"}})
        assert wp.podcast_rest_path("777") == "/wp/v2/episodes/777"

    def test_falls_back_to_episodes(self, mock_session):
        wp = _make_wp(mock_session)
        wp._rest_session.request.return_value = MagicMock(ok=False, status_code=404, text="")
        assert wp.podcast_rest_path("777") == "/wp/v2/episodes/777"


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


class TestAuthCookieMasking:
    def test_login_cookies_are_masked_after_dump_and_load(self, tmp_path):
        """Куки входа вырезаются из логов и текста ошибок, служебные остаются."""
        cookie_path = str(tmp_path / "cookie.json")
        source = RequestsCookieJar()
        source.set("wordpress_logged_in_abc", "login-cookie-value", domain="example.com", path="/")
        source.set("wordpress_sec_abc", "secure-cookie-value", domain="example.com", path="/")
        source.set("wordpress_test_cookie", "WP Cookie check", domain="example.com", path="/")

        writer = WordPress.__new__(WordPress)
        writer._session = MagicMock(cookies=source)
        writer._cookie_path = cookie_path
        try:
            assert writer._dump_cookies() is True
            dumped = mask_secrets("sent login-cookie-value and secure-cookie-value, WP Cookie check")
            default_masker.clear()

            reader = WordPress.__new__(WordPress)
            reader._session = MagicMock(cookies=RequestsCookieJar())
            reader._cookie_path = cookie_path
            assert reader._load_cookies() is True
            loaded = mask_secrets("sent login-cookie-value and secure-cookie-value, WP Cookie check")
        finally:
            default_masker.clear()

        assert dumped == loaded == "sent *** and ***, WP Cookie check"
