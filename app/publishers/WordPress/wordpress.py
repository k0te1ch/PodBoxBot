import json
import os
import pickle
import re
from datetime import datetime
from time import sleep

import pytz
import requests
from fake_useragent import UserAgent
from loguru import logger
from lxml import etree
from requests import Response
from requests.auth import HTTPBasicAuth

HTTP_TIMEOUT = 30
HTTP_RETRIES = 3
HTTP_BACKOFF_BASE = 2.0


class WordPress:
    """WordPress client for uploading posts via wp-admin form submission."""

    def __init__(
        self,
        wp_url: str,
        wp_login: str,
        wp_password: str,
        wp_app_password: str,
        cookie_path: str,
        timezone: str = "Europe/Moscow",
    ):
        self._wp_url = wp_url.rstrip("/")
        self._wp_login = wp_login
        self._wp_password = wp_password
        self._app_auth = HTTPBasicAuth(wp_login, wp_app_password) if wp_app_password else None
        self._cookie_path = cookie_path
        self._timezone = pytz.timezone(timezone)
        self._session: requests.Session | None = None
        self._user_agent = UserAgent().random
        self._make_session()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _dump_cookies(self) -> bool:
        if not self._cookie_path:
            raise ValueError("Cookie path cannot be empty")
        try:
            with open(self._cookie_path, "wb") as f:
                pickle.dump(self._session.cookies, f)
            return True
        except Exception as e:
            logger.error(f"Error saving cookies: {e}")
            return False

    def _load_cookies(self) -> bool:
        if os.path.exists(self._cookie_path) and os.path.getsize(self._cookie_path) > 0:
            with open(self._cookie_path, "rb") as f:
                self._session.cookies.update(pickle.load(f))
            return True
        return False

    @staticmethod
    def _extract_login_error(html: str) -> str | None:
        """Pull the inner text of WP's <div id="login_error"> if present.

        Modern WP renders auth failures inline as
            <div id="login_error" role="alert">
              <strong>Error:</strong> The password you entered ...
            </div>
        That's the single best signal the form was rejected (vs. genuine
        cookie/CSRF problems).
        """
        m = re.search(
            r'<div[^>]*id=["\']login_error["\'][^>]*>(.*?)</div>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if not m:
            return None
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        return re.sub(r"\s+", " ", text).strip()

    def _login(self) -> bool:
        """Form-based wp-login.php auth. Sets auth cookies in session on success.

        WP requires the wordpress_test_cookie to be present on POST — a JS
        snippet on the login page sets it client-side, so a bare POST without
        the cookie is rejected silently (server returns the login page again).
        We set it explicitly. We disable redirect-following so we can detect
        success directly by the 302 + Location header WP emits on successful
        auth; that's far more reliable than scraping a legacy JS redirect from
        the rendered body.
        """
        url = f"{self._wp_url}/wp-login.php"

        # Prime cookies: a GET lets WP set any cookies it expects to see
        # back on POST (some setups also set wordpress_test_cookie here).
        try:
            self._session.get(url, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            logger.warning(f"Login priming GET failed: {e!r} — proceeding anyway")

        # WP's JS sets this client-side; the form is rejected without it.
        self._session.cookies.set("wordpress_test_cookie", "WP Cookie check")
        self._session.cookies.set("wp_lang", "ru_RU")

        form = {
            "log": self._wp_login,
            "pwd": self._wp_password,
            "rememberme": "forever",
            "wp-submit": "Войти",
            "redirect_to": f"{self._wp_url}/wp-admin/",
            "testcookie": "1",
        }
        try:
            s = self._session.post(url, data=form, timeout=HTTP_TIMEOUT, allow_redirects=False)
        except requests.RequestException as e:
            logger.error(f"Login POST failed: {e!r}")
            return False

        # Successful auth: WP emits 302 to redirect_to AND sets wordpress_logged_in_<hash>.
        if s.status_code in (301, 302):
            location = s.headers.get("Location", "")
            has_auth_cookie = any(
                c.name.startswith("wordpress_logged_in_") for c in self._session.cookies
            )
            if has_auth_cookie:
                logger.debug(f"Login ok (redirect to {location})")
                return self._dump_cookies()
            logger.warning(
                f"Login got 3xx to {location!r} but no wordpress_logged_in_* cookie was set; "
                f"cookies={[c.name for c in self._session.cookies]}"
            )
            return False

        # 200 with form re-served = auth rejected. Try to surface why.
        err = self._extract_login_error(s.text) if s.status_code == 200 else None
        if err:
            logger.error(f"WordPress rejected login: {err}")
        else:
            logger.warning(
                f"Login did not produce expected 302 (status={s.status_code}); "
                f"no <div id=\"login_error\"> in body; body[:300]={s.text[:300]!r}"
            )
        return False

    def _check_session(self) -> bool:
        """True iff the cookie session has a valid WP login.

        Done by hitting wp-admin with allow_redirects=False: an authed session
        gets 200, an anonymous one gets 302 to wp-login.php. Robust across WP
        versions; the previous text-scrape heuristic broke on WP 6.x.
        """
        try:
            r = self._session.get(
                f"{self._wp_url}/wp-admin/", timeout=HTTP_TIMEOUT, allow_redirects=False
            )
        except requests.RequestException as e:
            logger.warning(f"Session check request failed: {e!r}")
            return False
        if r.status_code in (301, 302):
            loc = r.headers.get("Location", "")
            if "wp-login.php" in loc:
                return False
        return r.status_code == 200

    def _make_session(self) -> requests.Session:
        self._session = requests.Session()
        self._session.headers = {"User-Agent": self._user_agent}
        if not (self._load_cookies() and self._check_session()):
            self._login()
        return self._session

    def close(self):
        if self._session:
            self._session.close()

    def _rest_request(self, method: str, path: str, *, json_body: dict | None = None) -> Response:
        """Authenticated REST API request via Application Password.

        Uses a bare `requests.request` (not the cookie session) on purpose:
        WordPress prefers cookie auth over basic auth when both are present,
        and cookie auth on REST API requires an `X-WP-Nonce` header — without
        it the server returns 401 `rest_forbidden`. Sending only Basic auth
        avoids that ambiguity.
        """
        if self._app_auth is None:
            raise RuntimeError("WP_APP_PASSWORD is not configured; REST API call impossible")
        url = f"{self._wp_url}/wp-json{path}"
        try:
            r = requests.request(
                method,
                url,
                json=json_body,
                auth=self._app_auth,
                headers={"Accept": "application/json", "User-Agent": self._user_agent},
                timeout=HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.error(f"REST {method} {path} transport failed: {e!r}")
            raise RuntimeError(f"REST {method} {path} transport failed: {e!r}") from e
        if not r.ok:
            logger.error(
                f"REST {method} {path} returned HTTP {r.status_code}; body[:500]={r.text[:500]!r}"
            )
            raise RuntimeError(f"REST {method} {path} returned HTTP {r.status_code}")
        return r

    @staticmethod
    def _extract_podlove_vue(html: str) -> dict | None:
        """Parse the `podlove_vue` JS object embedded in the post-new page.

        The page reserves both a WP post_id and a Podlove episode_id and prints
        them as a JSON literal in an inline <script>. Returns the parsed dict
        (with int post_id / episode_id) or None if not found / unparseable.
        """
        m = re.search(r"var\s+podlove_vue\s*=\s*(\{.*?\})\s*;", html)
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        try:
            data["post_id"] = int(data["post_id"])
            data["episode_id"] = int(data["episode_id"])
        except (KeyError, ValueError, TypeError):
            return None
        return data

    @staticmethod
    def _format_duration(seconds) -> str:
        try:
            total = int(seconds)
        except (TypeError, ValueError):
            return str(seconds)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _update_podlove_episode(self, episode_id: int, info: dict) -> None:
        payload = {
            "title": info["title"],
            "summary": info["comment"],
            "number": int(info["number"]) if str(info["number"]).isdigit() else info["number"],
            "slug": info["slug"],
            "duration": self._format_duration(info["duration"]),
            "type": "full",
        }
        self._rest_request("POST", f"/podlove/v2/episodes/{episode_id}", json_body=payload)
        logger.debug(f"Podlove episode {episode_id} metadata updated")

    def _update_podlove_chapters(self, episode_id: int, chapters: list) -> None:
        payload = {"chapters": [{"start": start, "title": title} for start, title in chapters]}
        self._rest_request("POST", f"/podlove/v2/chapters/{episode_id}", json_body=payload)
        logger.debug(f"Podlove episode {episode_id} chapters updated ({len(chapters)} entries)")

    def _get_with_retry(self, url: str) -> Response:
        """GET with timeout and exponential backoff on transport/5xx errors.

        Retries on connection errors, timeouts, and 5xx responses. Returns
        the final Response (which may still be a 4xx) once retries are
        exhausted or a non-5xx is received. Raises RuntimeError if every
        attempt fails at the transport layer.
        """
        last_error: Exception | None = None
        for attempt in range(1, HTTP_RETRIES + 1):
            try:
                r = self._session.get(url, timeout=HTTP_TIMEOUT)
            except requests.RequestException as e:
                last_error = e
                logger.warning(f"GET {url} failed on attempt {attempt}/{HTTP_RETRIES}: {e!r}")
            else:
                if r.status_code < 500:
                    return r
                last_error = RuntimeError(f"server returned {r.status_code}")
                logger.warning(
                    f"GET {url} returned {r.status_code} on attempt {attempt}/{HTTP_RETRIES}; "
                    f"body[:300]={r.text[:300]!r}"
                )
            if attempt < HTTP_RETRIES:
                sleep(HTTP_BACKOFF_BASE ** (attempt - 1))
        raise RuntimeError(f"GET {url} failed after {HTTP_RETRIES} attempts: {last_error!r}")

    def upload_post(self, info: dict) -> bool:
        """Upload a podcast post to WordPress. Returns True on success."""
        logger.debug("Starting post upload process")
        post_new_url = f"{self._wp_url}/wp-admin/post-new.php?post_type=podcast"
        response = self._get_with_retry(post_new_url)

        if not response.ok:
            logger.error(
                f"wp-admin post-new page returned HTTP {response.status_code}; "
                f"body[:500]={response.text[:500]!r}"
            )
            raise RuntimeError(f"WordPress returned HTTP {response.status_code} for post-new page")

        logger.debug(f"Retrieved post content from WordPress (status={response.status_code})")

        html_dom = etree.HTML(response.content, etree.HTMLParser())
        podcastID = info["number"]
        name = info["title"]
        summary = info["comment"]
        chapters = ""
        for time_str, chapterName in info["chapters"]:
            chapters += f"[skipto time={time_str}]{time_str}[/skipto] — {chapterName}\n"

        time = datetime.now(self._timezone)

        months = (
            "января",
            "февраля",
            "марта",
            "апреля",
            "мая",
            "июня",
            "июля",
            "августа",
            "сентября",
            "октября",
            "ноября",
            "декабря",
        )
        timeStr = f"{time.day} {months[time.month - 1]} {time.year}"

        form = {
            "post_title": f"Разговорный жанр — {podcastID}",
            "content": f"""<span style="font-size: large;">{name.replace(podcastID + ". ", "")}</span><code>
</code>
<b><i>Описание:</i></b>
<code>{summary}
</code>
<!--more--><b><i>Таймлайн:</i></b>
{chapters}
<code>
</code>Всё это вы услышите в {podcastID}-м эпизоде подкаста «Разговорный жанр».
[podlove-template template="subscriptions"]
<span style="font-size: small;">Дата записи: {timeStr}</span>""",
            "post_name": f"Разговорный жанр — {podcastID}",
            "post_category[]": "3",
            "newcategory": "Название новой рубрики",
            "newcategory_parent": "-1",
            "trackback_url": "",
            "metakeyselect": "big_post",
            "metakeyinput": "",
            "metavalue": "1",
            "comment_status": "open",
            "ping_status": "open",
            "post_author_override": "361",
            "tax_input[shows]": "0",
            "referredby": f"{self._wp_url}/wp-admin/profile.php",
            "_wp_original_http_referer": f"{self._wp_url}/wp-admin/profile.php",
            "tax_input[post_tag]": ",".join(info["tags"]),
            "newtag[post_tag]": "",
            "_thumbnail_id": "6038",
        }
        form_element = html_dom.find('.//form[@name="post"]')
        if form_element is None:
            logger.warning(
                f"Post form not found on first try — re-logging in; "
                f"body[:500]={response.text[:500]!r}"
            )
            if not self._login():
                raise RuntimeError("Re-login to WordPress failed")
            response = self._get_with_retry(post_new_url)
            if not response.ok:
                logger.error(
                    f"wp-admin post-new page returned HTTP {response.status_code} after re-login; "
                    f"body[:500]={response.text[:500]!r}"
                )
                raise RuntimeError(
                    f"WordPress returned HTTP {response.status_code} for post-new page after re-login"
                )
            html_dom = etree.HTML(response.content, etree.HTMLParser())
            form_element = html_dom.find('.//form[@name="post"]')
            if form_element is None:
                logger.error(
                    f"Post form still not found after re-login; "
                    f"body[:500]={response.text[:500]!r}"
                )
                raise RuntimeError("Failed to find WordPress post form after re-login")

        for field in form_element.xpath('.//input[@type="hidden"]'):
            field = field.attrib
            if field["name"] not in form:
                form[field["name"]] = field["value"]

        podlove_vue = self._extract_podlove_vue(response.text)
        if podlove_vue is None:
            logger.error(
                f"Could not extract podlove_vue from post-new page; "
                f"body[:500]={response.text[:500]!r}"
            )
            raise RuntimeError("podlove_vue (post_id/episode_id) not found in post-new page")
        logger.debug(
            f"Podlove reserved post_id={podlove_vue['post_id']}, "
            f"episode_id={podlove_vue['episode_id']}"
        )

        logger.debug("Submitting post data to WordPress")
        try:
            response = self._session.post(
                f"{self._wp_url}/wp-admin/post.php", data=form, timeout=HTTP_TIMEOUT
            )
        except requests.RequestException as e:
            logger.error(f"Post submit failed: {e!r}")
            raise RuntimeError(f"WordPress post submit failed: {e!r}") from e
        logger.debug(f"Uploaded post with response code: {response.status_code}")

        if response.status_code not in (200, 301, 302):
            logger.error(
                f"Post submit returned HTTP {response.status_code}; "
                f"body[:500]={response.text[:500]!r}"
            )
            return False

        self._dump_cookies()

        logger.debug(
            f"Post saved (post_id={podlove_vue['post_id']}); "
            f"updating Podlove episode_id={podlove_vue['episode_id']}"
        )
        self._update_podlove_episode(podlove_vue["episode_id"], info)
        if info.get("chapters"):
            self._update_podlove_chapters(podlove_vue["episode_id"], info["chapters"])
        return True
