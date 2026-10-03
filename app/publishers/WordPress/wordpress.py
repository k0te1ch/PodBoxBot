import re
from datetime import datetime

import pytz
import requests
from fake_useragent import UserAgent
from loguru import logger
from lxml import etree
from podlove import PodloveMixin
from requests.auth import HTTPBasicAuth
from wp_http import WordPressHttpMixin

_MONTHS = (
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


class WordPress(WordPressHttpMixin, PodloveMixin):
    """WordPress client for uploading posts via wp-admin form submission.

    Транспорт (куки, bot-protection, ретраи) — в :class:`WordPressHttpMixin`,
    Podlove REST — в :class:`PodloveMixin`.
    """

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
        self.last_post_id: str | None = None
        # Отдельная сессия под REST (Application Password). Cookie-сессия
        # для form-логина и REST-сессия живут раздельно, потому что WP
        # предпочитает cookie-auth над Basic при наличии обоих — здесь
        # нужно только Basic. Bot-protection cookie (bpc) выставляется
        # независимо в каждой сессии при первом запросе.
        self._rest_session: requests.Session = requests.Session()
        self._rest_session.headers.update({"Accept": "application/json", "User-Agent": (ua := UserAgent().random)})
        self._user_agent = ua
        self._make_session()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

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
        # Also lets _request solve any bot-protection challenge before
        # we try to POST credentials.
        try:
            self._request(self._session, "GET", url)
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
            s = self._request(self._session, "POST", url, data=form, allow_redirects=False)
        except requests.RequestException as e:
            logger.error(f"Login POST failed: {e!r}")
            return False

        # Successful auth: WP emits 302 to redirect_to AND sets wordpress_logged_in_<hash>.
        if s.status_code in (301, 302):
            location = s.headers.get("Location", "")
            has_auth_cookie = any(c.name.startswith("wordpress_logged_in_") for c in self._session.cookies)
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
                f'no <div id="login_error"> in body; body[:300]={s.text[:300]!r}'
            )
        return False

    def _check_session(self) -> bool:
        """True iff the cookie session has a valid WP login.

        Done by hitting wp-admin with allow_redirects=False: an authed session
        gets 200, an anonymous one gets 302 to wp-login.php. Robust across WP
        versions; the previous text-scrape heuristic broke on WP 6.x.
        """
        try:
            r = self._request(self._session, "GET", f"{self._wp_url}/wp-admin/", allow_redirects=False)
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
        if self._rest_session:
            self._rest_session.close()

    @staticmethod
    def post_title(number: str) -> str:
        return f"Разговорный жанр — {number}"

    @staticmethod
    def _format_recording_date(info: dict, now: datetime) -> str:
        """Дата записи для тела поста: ``recording_date`` из шаблона (ISO), иначе ``now``."""
        when = now
        recording_iso = info.get("recording_date")
        if recording_iso:
            try:
                when = datetime.strptime(recording_iso, "%Y-%m-%d")
            except ValueError as e:
                logger.warning(f"Invalid recording_date {recording_iso!r} ({e}); falling back to today")
        return f"{when.day} {_MONTHS[when.month - 1]} {when.year}"

    @staticmethod
    def _publish_date_fields(info: dict) -> dict[str, str]:
        """Дата публикации в полях редактора записи (``aa``, ``mm``, ``jj``, ``hh``, ``mn``).

        ``edit_date`` говорит WordPress взять дату записи из этих полей.
        Запись остаётся черновиком: дата сработает, когда редактор нажмёт
        «Опубликовать» (будущая дата превратит это в отложенную публикацию).
        Без ``publish_at`` полей нет, и WordPress ведёт себя как раньше.
        """
        raw = info.get("publish_at")
        if not raw:
            return {}
        try:
            when = datetime.strptime(raw, "%Y-%m-%dT%H:%M")
        except ValueError as e:
            logger.warning(f"Invalid publish_at {raw!r} ({e}); the draft keeps the default date")
            return {}
        return {
            "edit_date": "1",
            "aa": f"{when.year:04d}",
            "mm": f"{when.month:02d}",
            "jj": f"{when.day:02d}",
            "hh": f"{when.hour:02d}",
            "mn": f"{when.minute:02d}",
            "ss": "00",
        }

    def _build_form(self, info: dict) -> dict[str, str]:
        number = info["number"]
        chapters = "".join(
            f"[skipto time={time_str}]{time_str}[/skipto] — {chapter}\n"
            for time_str, chapter in info.get("chapters") or []
        )
        # Шаблон без Chapters: без пустого заголовка «Таймлайн».
        timeline = f"<b><i>Таймлайн:</i></b>\n{chapters}" if chapters else ""
        date_str = self._format_recording_date(info, datetime.now(self._timezone))
        return {
            "post_title": self.post_title(number),
            "content": f"""<span style="font-size: large;">{info["title"].replace(number + ". ", "")}</span>
<b><i>Описание:</i></b>
{info["comment"]}
<!--more-->{timeline}
Всё это вы услышите в {number}-м эпизоде подкаста «Разговорный жанр».
[podlove-template template="subscriptions"]
<span style="font-size: small;">Дата записи: {date_str}</span>""",
            "post_name": self.post_title(number),
            "post_category[]": "3",
            "newcategory": "Название новой рубрики",
            "newcategory_parent": "-1",
            "trackback_url": "",
            "comment_status": "open",
            "ping_status": "open",
            "post_author_override": "361",
            "tax_input[shows]": "0",
            # Подложные контрибьюторы Podlove (id 1 и 3) — без них эпизод
            # сохраняется без авторов и не показывает их в плеере.
            "episode_contributor[0][1][id]": "1",
            "episode_contributor[0][1][comment]": "",
            "episode_contributor[0][3][id]": "3",
            "episode_contributor[0][3][comment]": "",
            "referredby": f"{self._wp_url}/wp-admin/profile.php",
            "_wp_original_http_referer": f"{self._wp_url}/wp-admin/profile.php",
            "tax_input[post_tag]": ",".join(info.get("tags") or []),
            "newtag[post_tag]": "",
            "_thumbnail_id": "6038",
            **self._publish_date_fields(info),
        }

    def _fetch_editor_page(self, url: str):
        """GET страницы редактора; при отсутствии формы — один перелогин и повтор."""
        for attempt in (1, 2):
            response = self._get_with_retry(url)
            if not response.ok:
                logger.error(f"{url} returned HTTP {response.status_code}; body[:500]={response.text[:500]!r}")
                raise RuntimeError(f"WordPress returned HTTP {response.status_code} for {url}")
            form_element = etree.HTML(response.content, etree.HTMLParser()).find('.//form[@name="post"]')
            if form_element is not None:
                return response, form_element
            if attempt == 2:
                logger.error(f"Post form still not found after re-login; body[:500]={response.text[:500]!r}")
                raise RuntimeError("Failed to find WordPress post form after re-login")
            logger.warning(f"Post form not found on first try — re-logging in; body[:500]={response.text[:500]!r}")
            if not self._login():
                raise RuntimeError("Re-login to WordPress failed")
        raise AssertionError("unreachable")

    def upload_post(self, info: dict) -> bool:
        """Создаёт черновик эпизода (или обновляет уже созданный) и заполняет Podlove.

        Идемпотентно: если черновик с таким заголовком уже есть (повтор после
        частичного успеха), форма отправляется поверх него, а не создаёт
        второй пост.
        """
        logger.debug("Starting post upload process")
        form = self._build_form(info)
        existing = self.find_draft(form["post_title"])
        if existing:
            post_id, episode_id = existing
            logger.info(f"Reusing existing draft post_id={post_id} episode_id={episode_id}")
            page_url = f"{self._wp_url}/wp-admin/post.php?post={post_id}&action=edit"
        else:
            page_url = f"{self._wp_url}/wp-admin/post-new.php?post_type=podcast"
        response, form_element = self._fetch_editor_page(page_url)

        for field in form_element.xpath('.//input[@type="hidden"]'):
            name = field.get("name")
            if name and name not in form:
                form[name] = field.get("value", "")

        if not existing:
            podlove_vue = self._extract_podlove_vue(response.text)
            if podlove_vue is None:
                logger.error(f"Could not extract podlove_vue from post-new page; body[:500]={response.text[:500]!r}")
                raise RuntimeError("podlove_vue (post_id/episode_id) not found in post-new page")
            post_id, episode_id = podlove_vue["post_id"], podlove_vue["episode_id"]
            logger.debug(f"Podlove reserved post_id={post_id}, episode_id={episode_id}")

        logger.debug("Submitting post data to WordPress")
        try:
            response = self._request(self._session, "POST", f"{self._wp_url}/wp-admin/post.php", data=form)
        except requests.RequestException as e:
            logger.error(f"Post submit failed: {e!r}")
            raise RuntimeError(f"WordPress post submit failed: {e!r}") from e
        logger.debug(f"Uploaded post with response code: {response.status_code}")

        if response.status_code not in (200, 301, 302):
            logger.error(f"Post submit returned HTTP {response.status_code}; body[:500]={response.text[:500]!r}")
            return False
        # Протухшая сессия: post.php редиректит на wp-login.php, requests идёт
        # следом и получает 200 — без этой проверки это выглядело бы успехом.
        if "wp-login.php" in str(getattr(response, "url", "") or ""):
            raise RuntimeError("WordPress redirected post submit to wp-login.php (session expired)")

        self._dump_cookies()
        self.last_post_id = str(post_id)

        logger.debug(f"Post saved (post_id={post_id}); updating Podlove episode_id={episode_id}")
        self._update_podlove_episode(episode_id, info)
        if info.get("chapters"):
            self._update_podlove_chapters(episode_id, info["chapters"])
        return True
