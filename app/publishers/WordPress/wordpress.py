import os
import pickle
import re
from datetime import datetime

import pytz
import requests
from fake_useragent import UserAgent
from loguru import logger
from lxml import etree
from requests import Response


class WordPress:
    """WordPress client for uploading posts via wp-admin form submission."""

    def __init__(
        self, wp_url: str, wp_login: str, wp_password: str, cookie_path: str, timezone: str = "Europe/Moscow"
    ):
        self._wp_url = wp_url.rstrip("/")
        self._wp_login = wp_login
        self._wp_password = wp_password
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

    def _login(self) -> bool:
        url = f"{self._wp_url}/wp-login.php"
        self._session.cookies["wordpress_test_cookie"] = "WP Cookie check"
        self._session.cookies["wp_lang"] = "ru_RU"
        form = {
            "log": self._wp_login,
            "pwd": self._wp_password,
            "rememberme": "forever",
            "wp-submit": "Войти",
            "redirect_to": f"{self._wp_url}/wp-admin/",
            "testcookie": 1,
        }
        s = self._session.post(url, data=form)

        if (
            s.status_code == 200
            and f'document.location.href="{self._wp_url.replace("https", "http")}/wp-login.php' in s.text
        ):
            cookie_matches = re.findall(r'document\.cookie="(.*?)";', s.text)
            for match in cookie_matches:
                cookie_parts = match.split(";")
                for part in cookie_parts:
                    if "=" in part:
                        name, value = part.strip().split("=", 1)
                        self._session.cookies[name.strip()] = value.strip()

        s = self._session.post(url, data=form)
        if (
            s.status_code == 200
            and f'document.location.href="{self._wp_url.replace("https", "http")}/wp-admin' in s.text
        ):
            return self._dump_cookies()
        return False

    def _check_session(self) -> bool:
        return (
            f'document.location.href="{self._wp_url.replace("https", "http")}/wp-login.php?redirect_to='
            not in self._session.get(f"{self._wp_url}/wp-admin/").text
        )

    def _make_session(self) -> requests.Session:
        self._session = requests.Session()
        self._session.headers = {"User-Agent": self._user_agent}
        if not (self._load_cookies() and self._check_session()):
            self._login()
        return self._session

    def close(self):
        if self._session:
            self._session.close()

    def upload_post(self, info: dict) -> bool:
        """Upload a podcast post to WordPress. Returns True on success."""
        logger.debug("Starting post upload process")
        post = self._session.get(f"{self._wp_url}/wp-admin/post-new.php?post_type=podcast").content

        logger.debug("Retrieved post content from WordPress")

        html_dom = etree.HTML(post, etree.HTMLParser())
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
            "_podlove_meta[number]": podcastID,
            "_podlove_meta[title]": name,
            "_podlove_meta[summary]": summary,
            "_podlove_meta[type]": "full",
            "episode_contributor[0][1][id]": "1",
            "episode_contributor[0][1][comment]": "",
            "episode_contributor[0][3][id]": "3",
            "episode_contributor[0][3][comment]": "",
            "_podlove_meta[recording_date]": time.strftime("%Y-%m-%d"),
            "_podlove_meta[slug]": info["slug"],
            "_podlove_meta[chapters]": "\n".join(" ".join(x) for x in info["chapters"]),
            "_podlove_meta[duration]": info["duration"],
            "_podlove_meta[episode_assets][1]": "on",
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
            "_podlove_meta[subtitle]": "",
            "_thumbnail_id": "6038",
        }
        form_element = html_dom.find('.//form[@name="post"]')
        if form_element is None:
            logger.error("Could not find post form in WordPress page — session may be expired")
            # Retry login and try once more
            self._login()
            post = self._session.get(f"{self._wp_url}/wp-admin/post-new.php?post_type=podcast").content
            html_dom = etree.HTML(post, etree.HTMLParser())
            form_element = html_dom.find('.//form[@name="post"]')
            if form_element is None:
                raise RuntimeError("Failed to find WordPress post form after re-login")

        for field in form_element.xpath('.//input[@type="hidden"]'):
            field = field.attrib
            if field["name"] not in form:
                form[field["name"]] = field["value"]

        logger.debug("Submitting post data to WordPress")
        response: Response = self._session.post(f"{self._wp_url}/wp-admin/post.php", data=form)
        logger.debug(f"Uploaded post with response code: {response.status_code}")

        if response.status_code in (200, 301, 302):
            self._dump_cookies()
            return True
        return False
