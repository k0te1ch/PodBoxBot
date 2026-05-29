import os
import pickle
import re
import warnings
from datetime import datetime

import feedparser
import requests
from fake_useragent import UserAgent
from loguru import logger
from lxml import etree
from requests import Response

from config import TIMEZONE, WP_COOKIE_PATH, WP_LOGIN, WP_PASSWORD, WP_URL

# TODO make this async
# TODO: обернуть всё в определённый
# TODO: Проблема с куками и сессией


class WordPress:
    """
    A class for interacting with a WordPress site via the API.

    Attributes:
    _session (requests.Session): A session for sending HTTP requests.
    _filename (str): The path to the file for saving cookies.
    _userAgent (fake_useragent.UserAgent): A fake random user agent.

    Methods:
    __init__: Initialize the class and create a session.
    __enter__: Enter method for context management.
    __exit__: Exit method for context management.
    _dump_cookies: Save cookies to a file.
    _load_cookies: Load cookies from a file.
    _login: Authenticate on a WordPress site.
    _check_session: Check the session status.
    _make_session: Create a session with cookies in mind.
    close: Close the session.
    upload_post: Upload a new post to the site.
    get_last_post_id: Get the ID of the last uploaded post.
    """

    _instance = None
    _session: requests.Session = requests.Session()
    _filename: str = WP_COOKIE_PATH
    _userAgent: UserAgent = UserAgent().random

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True  # Флаг, чтобы инициализация выполнялась только раз
            self._session = None
            self._make_session()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _dump_cookies(self) -> bool:
        if not self._filename:
            raise ValueError("Имя файла не может быть пустым")

        try:
            with open(self._filename, "wb") as f:
                pickle.dump(self._session.cookies, f)
            return True
        except Exception as e:
            print(f"Ошибка сохранения куков: {e}")
            return False

    def _load_cookies(self) -> bool:
        if os.path.exists(self._filename) and os.path.getsize(self._filename) > 0:
            with open(self._filename, "rb") as f:
                self._session.cookies.update(pickle.load(f))
            return True
        return False

    def _login(self) -> bool:
        url = f"{WP_URL}/wp-login.php"
        self._session.cookies["wordpress_test_cookie"] = "WP Cookie check"
        self._session.cookies["wp_lang"] = "ru_RU"
        form = {
            "log": WP_LOGIN,
            "pwd": WP_PASSWORD,
            "rememberme": "forever",
            "wp-submit": "Войти",
            "redirect_to": f"{WP_URL}/wp-admin/",
            "testcookie": 1,
        }
        s = self._session.post(url, data=form)

        if (
            s.status_code == 200
            and f'document.location.href="{WP_URL.replace("https", "http")}/wp-login.php' in s.text
        ):
            cookie_matches = re.findall(r'document\.cookie="(.*?)";', s.text)
            for match in cookie_matches:
                cookie_parts = match.split(";")
                for part in cookie_parts:
                    if "=" in part:
                        name, value = part.strip().split("=", 1)
                        self._session.cookies[name.strip()] = value.strip()

        s = self._session.post(url, data=form)
        if s.status_code == 200 and f'document.location.href="{WP_URL.replace("https", "http")}/wp-admin' in s.text:
            return self._dump_cookies()
        return False

    def _check_session(self) -> bool:
        return (
            f'document.location.href="{WP_URL.replace("https", "http")}/wp-login.php?redirect_to='
            not in self._session.get(f"{WP_URL}/wp-admin/").text
        )

    def _make_session(self) -> requests.Session:
        self._session.headers = {"User-Agent": self._userAgent}
        if not (self._load_cookies() and self._check_session()):
            self._login()

        return self._session

    def close(self):
        self._session.close()

    def upload_post(self, info: dict) -> str:
        logger.debug("Starting post upload process")
        post = self._session.get(f"{WP_URL}/wp-admin/post-new.php?post_type=podcast").content

        logger.debug("Retrieved post content from WordPress")

        #! TODO check if exist

        html_dom = etree.HTML(post, etree.HTMLParser())
        podcastID = info["number"]
        name = info["title"]
        summary = info["comment"]
        chapters = ""
        for time, chapterName in info["chapters"]:
            chapters += f"[skipto time={time}]{time}[/skipto] — {chapterName}\n"

        time = datetime.now(TIMEZONE)

        timeStr = f"{time.day} {('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')[time.month - 1]} {time.year}"  # TODO Locale settings!

        form = {  # TODO refactor this (name.replace...)
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
            "_podlove_meta[title]": f"Разговорный жанр — {podcastID}",
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
            "referredby": f"{WP_URL}/wp-admin/profile.php",
            "_wp_original_http_referer": f"{WP_URL}/wp-admin/profile.php",
            "tax_input[post_tag]": ",".join(info["tags"]),
            "newtag[post_tag]": "",
            "_podlove_meta[subtitle]": "",
            "_thumbnail_id": "6038",
        }
        form_element = html_dom.find('.//form[@name="post"]')
        for field in form_element.xpath('.//input[@type="hidden"]'):
            field = field.attrib
            if field["name"] not in form:
                form[field["name"]] = field["value"]

        logger.debug("Submitting post data to WordPress")
        response: Response = self._session.post(f"{WP_URL}/wp-admin/post.php", data=form)
        logger.debug(f"Uploaded post with response code: {response.status_code}")  # TODO

    @staticmethod
    def get_last_post_ID() -> str:  # Deprecated
        warnings.warn("get_last_post_ID is deprecated", DeprecationWarning, stacklevel=2)
        feed = feedparser.parse(f"{WP_URL}/feed/podcast/")
        return feed["entries"][0]["itunes_episode"]
