"""Эпизод в разделе подкастов сообщества vk.ru, закрытый для донов.

У официального API нет методов загрузки подкастов (podcasts.* только читают
каталог), поэтому этот режим повторяет запросы веб-интерфейса vk.ru по
сессии браузера (куки). Последовательность сверена с записью ручной
публикации 25.10.2026: обычный выпуск (privacy=0) и послешоу (privacy=2,
«Только донам»).

    POST vk.ru/al_podcasts.php  act=a_add_box      → audio_upload.url, галерея обложек
    POST <audio_upload.url>     multipart file     → ответ загрузчика (JSON)
    POST vk.ru/al_audio.php     act=done_add       go_uploader_response → эпизод + hash
    POST vk.ru/al_podcasts.php  act=a_edit         title, desc, cover_id, privacy (замок)
    POST login.vk.ru/?act=web_token                → access_token веб-приложения
    POST api.vk.ru/method/wall.post                attachments=podcast<owner>_<id>

Замок ставится на сам эпизод (``privacy=2``), пост на стене только
публикует его: до публикации записи эпизод никому не виден. Внутренние
запросы VK может поменять; тогда ошибка придёт админу в бот, а запасной
путь (``VK_MEDIA=video`` или ``doc``) остаётся на официальном API.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import string
from pathlib import Path

import httpx
from loguru import logger
from sagenza_tgbot_sdk.masking import register_secrets
from sagenza_tgbot_sdk.resilience import PermanentError
from vk_client import raise_for_error

WEB_URL = "https://vk.ru"
LOGIN_URL = "https://login.vk.ru/"
API_URL = "https://api.vk.ru/method"
# Веб-приложение vk.ru: его id и версия API стоят в запросах страницы.
WEB_APP_ID = "6287487"
WEB_API_VERSION = "5.289"
PRIVACY_ALL = 0
PRIVACY_DONUT = 2
_TIMEOUT = httpx.Timeout(60.0, read=600.0, write=600.0)
_COVER_RE = re.compile(r'data-item-id="(-?\d+_\d+)"')


class VkSessionError(PermanentError):
    HINT = (
        "Обновите secrets/vk/vk_session.json: войдите на vk.ru и выполните "
        "`python smoke.py import-cookie` (см. app/publishers/VK/SMOKE.md)."
    )

    def __init__(self, reason: str) -> None:
        super().__init__(f"VK: {reason}. {self.HINT}")


class VkWebError(RuntimeError):
    pass


def parse_cookie_header(header: str) -> dict[str, str]:
    """Строка Cookie из DevTools → словарь имя: значение."""
    cookies = {}
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            cookies[name] = value
    return cookies


def load_session(path: str) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise VkSessionError(f"нет файла сессии {path}") from e
    except ValueError as e:
        raise VkSessionError(f"файл сессии {path} повреждён") from e
    cookies = raw.get("cookies") if isinstance(raw, dict) else None
    if not isinstance(cookies, dict) or not cookies:
        raise VkSessionError(f"в {path} нет куки vk.ru")
    # Куки сессии не должны попасть в логи и в текст ошибки, который уходит боту.
    register_secrets(*(str(value) for value in cookies.values() if len(str(value)) >= 8))
    return raw


def save_session(path: str, cookie_header: str, user_agent: str | None) -> int:
    cookies = parse_cookie_header(cookie_header)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"cookies": cookies, "user_agent": user_agent}), encoding="utf-8")
    return len(cookies)


def _payload(what: str, body: dict) -> list:
    payload = body.get("payload") if isinstance(body, dict) else None
    if not isinstance(payload, list) or not payload:
        raise VkWebError(f"VK {what}: нет payload в ответе")
    if str(payload[0]) != "0":
        raise VkWebError(f"VK {what}: код {payload[0]} {str(payload[1:])[:300]}")
    return payload[1] if len(payload) > 1 else []


class VkPodcastClient:
    def __init__(
        self,
        session_file: str,
        group_id: int | None,
        privacy: int = PRIVACY_DONUT,
        cover_id: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.session_file = session_file
        self.group_id = group_id
        self.privacy = privacy
        self.cover_id = cover_id
        self._http = http
        self._token: str | None = None

    @property
    def owner_id(self) -> str:
        return f"-{self.group_id}"

    @property
    def podcasts_page(self) -> str:
        return f"{WEB_URL}/podcasts-{self.group_id}"

    async def _client(self) -> httpx.AsyncClient:
        if not self.group_id:
            raise PermanentError("VK: VK_GROUP_ID не задан")
        if self._http is None:
            session = await asyncio.to_thread(load_session, self.session_file)
            cookies = httpx.Cookies()
            for name, value in session["cookies"].items():
                cookies.set(name, value, domain=".vk.ru")
            self._http = httpx.AsyncClient(
                timeout=_TIMEOUT,
                headers={"User-Agent": session.get("user_agent") or "Mozilla/5.0"},
                cookies=cookies,
                follow_redirects=False,
            )
        return self._http

    async def _al(self, what: str, script: str, data: dict) -> list:
        """Запрос al_*.php так, как его шлёт страница подкастов."""
        http = await self._client()
        resp = await http.post(
            f"{WEB_URL}/{script}",
            data={**data, "al": "1"},
            headers={"X-Requested-With": "XMLHttpRequest", "Origin": WEB_URL, "Referer": self.podcasts_page},
        )
        if 300 <= resp.status_code < 400 or resp.status_code in (401, 403):
            raise VkSessionError(f"{what}: сессия не принята (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise VkWebError(f"VK {what} → HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as e:
            raise VkSessionError(f"{what}: вместо JSON пришла страница, похоже, вход сброшен") from e
        return _payload(what, body)

    async def open_add_box(self) -> tuple[str, list[str]]:
        """Окно «Добавить эпизод»: адрес загрузки mp3 и обложки из галереи подкаста."""
        boxhash = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        parts = await self._al(
            "a_add_box",
            "al_podcasts.php",
            {"act": "a_add_box", "audio_id": "", "boxhash": boxhash, "oid": self.owner_id, "ref": "podcasts"},
        )
        info = next((part for part in parts if isinstance(part, dict)), {})
        url = (info.get("audio_upload") or {}).get("url")
        if not url:
            raise VkSessionError("окно добавления эпизода без адреса загрузки, нет прав на подкасты сообщества")
        register_secrets(url)
        html = "".join(part for part in parts if isinstance(part, str))
        return url, _COVER_RE.findall(html)

    async def upload(self, url: str, path: str) -> str:
        """Грузит mp3 в загрузчик VK. Возвращает его ответ как есть (для done_add)."""
        http = await self._client()
        content = await asyncio.to_thread(Path(path).read_bytes)
        resp = await http.post(
            url, files={"file": (Path(path).name, content, "audio/mpeg")}, headers={"Origin": WEB_URL}
        )
        if resp.status_code >= 400:
            raise VkWebError(f"VK upload → HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as e:
            raise VkWebError("VK upload: ответ загрузчика не JSON") from e
        if not isinstance(body, dict) or body.get("error") or not body.get("hash"):
            raise VkWebError(f"VK upload: загрузчик не принял файл ({str(body)[:200]})")
        return resp.text

    async def add_episode(self, uploader_response: str) -> tuple[str, str]:
        """Создаёт эпизод из загруженного файла. Возвращает (episode_full_id, hash для a_edit)."""
        parts = await self._al(
            "done_add",
            "al_audio.php",
            {"act": "done_add", "go_uploader_response": uploader_response, "podcast": "1", "upldr": "1"},
        )
        try:
            episode, edit_hash = parts[0]
            full_id = f"{episode[1]}_{episode[0]}"
        except (IndexError, TypeError, ValueError) as e:
            raise VkWebError(f"VK done_add: неожиданный ответ {str(parts)[:300]}") from e
        return full_id, str(edit_hash)

    async def edit_episode(self, full_id: str, edit_hash: str, *, title: str, desc: str, cover_id: str) -> None:
        """Название, описание, обложка и доступ эпизода (privacy=2: только донам)."""
        parts = await self._al(
            "a_edit",
            "al_podcasts.php",
            {
                "act": "a_edit",
                "audio_full_id": "",
                "cover_id": cover_id,
                "desc": desc,
                "episode_full_id": full_id,
                "explicit": "",
                "hash": edit_hash,
                "no_export": "",
                "privacy": str(self.privacy),
                "ref": "podcasts",
                "title": title,
                "trailer": "",
            },
        )
        if self.privacy == PRIVACY_DONUT and not _is_paid(parts):
            raise PermanentError("VK: эпизод сохранён без замка для донов, проверьте, что VK Donut подключён")

    async def web_token(self) -> str:
        """access_token веб-приложения vk.ru из сессии (как его получает страница)."""
        if self._token is None:
            http = await self._client()
            resp = await http.post(
                LOGIN_URL,
                params={"act": "web_token"},
                data={"version": "1", "app_id": WEB_APP_ID, "access_token": ""},
                headers={"Origin": WEB_URL, "Referer": f"{WEB_URL}/"},
            )
            try:
                body = resp.json()
            except ValueError:
                body = {}
            token = (body.get("data") or {}).get("access_token") if body.get("type") == "okay" else None
            if not token:
                raise VkSessionError(f"login.vk.ru не выдал токен (HTTP {resp.status_code})")
            register_secrets(str(token))
            self._token = str(token)
        return self._token

    async def call(self, method: str, **params) -> dict | list:
        http = await self._client()
        token = await self.web_token()
        resp = await http.post(
            f"{API_URL}/{method}",
            params={"v": WEB_API_VERSION, "client_id": WEB_APP_ID},
            data={**{k: v for k, v in params.items() if v is not None}, "access_token": token},
            headers={"Origin": WEB_URL},
        )
        resp.raise_for_status()
        body = resp.json()
        raise_for_error(method, body)
        return body["response"]

    async def post(self, message: str, attachment: str) -> str:
        resp = await self.call(
            "wall.post",
            owner_id=self.owner_id,
            from_group=1,
            message=message,
            attachments=attachment,
            close_comments=0,
            mute_notifications=0,
            signed=0,
        )
        return str(resp["post_id"])

    async def prepare_episode(self, path: str, *, title: str, desc: str) -> str:
        """Загружает mp3 и сохраняет эпизод под замком. Возвращает вложение ``podcast<owner>_<id>``."""
        url, covers = await self.open_add_box()
        uploaded = await self.upload(url, path)
        full_id, edit_hash = await self.add_episode(uploaded)
        cover_id = self.cover_id or (covers[0] if covers else "")
        await self.edit_episode(full_id, edit_hash, title=title, desc=desc, cover_id=cover_id)
        logger.info(f"VK podcast episode {full_id} saved (privacy={self.privacy})")
        return f"podcast{full_id}"

    async def publish(self, path: str, *, title: str, desc: str, message: str) -> str:
        """Эпизод под замком и пост с ним на стене. Возвращает post_id."""
        attachment = await self.prepare_episode(path, title=title, desc=desc)
        post_id = await self.post(message, attachment)
        logger.success(f"VK podcast post published (id={post_id}, {attachment})")
        return post_id

    async def get_post(self, post_id: str) -> dict | None:
        resp = await self.call("wall.getById", posts=f"{self.owner_id}_{post_id}")
        items = resp.get("items", []) if isinstance(resp, dict) else resp
        return items[0] if items else None

    def post_url(self, post_id: str) -> str:
        return f"{WEB_URL}/wall{self.owner_id}_{post_id}"

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()


def _is_paid(parts: list) -> bool:
    """В ответе a_edit флаги эпизода лежат JSON-строкой: {"private": true, "paid": true}."""
    episode = parts[0] if parts and isinstance(parts[0], list) else []
    for item in episode:
        if isinstance(item, str) and item.startswith("{") and '"podcast"' in item:
            try:
                return bool(json.loads(item).get("paid"))
            except ValueError:
                return False
    return False
