"""Клиент Boosty: многошаговый upload+publish-флоу internal API редактора.

Официального API у Boosty нет, поэтому клиент повторяет запросы веб-редактора
(реверс из HAR, см. `.planning/spikes/boosty-sponsr-feasibility.md`,
«Verified upload+publish flow»):

    POST upload.boosty.to/audio {container_id,...}       → fileId
    POST upload.boosty.to/upload/{fileId}  (octet, чанки 5 МБ, X-PartNumber)
    POST upload.boosty.to/upload/{fileId}/complete
    POST upload.boosty.to/image {}                       → fileId  (обложка)
    PUT  api.boosty.to/v1/blog/{blog}/post_draft         — заполнить черновик
    POST api.boosty.to/v1/blog/{blog}/post_draft/publish/ → опубликованный пост
    GET  api.boosty.to/v1/blog/{blog}/post/{id}           — проверка
    DELETE api.boosty.to/v1/blog/{blog}/post/{id}         — удаление (смоук)

Три режима (``BOOSTY_PUBLISH_MODE``):

* ``publish`` — PUT черновика и publish: пост сразу виден подписчикам;
* ``draft`` — только PUT черновика (как автосейв редактора): пост ждёт в
  редакторе блога, опубликует его автор руками;
* ``scheduled`` — PUT и publish с ``publish_time`` (unix-время в секундах):
  отложенный пост, ``isPublished=false`` до наступления времени.

``publish_time`` на обоих запросах шлёт и веб-редактор Boosty (сверено с его
JS-бандлом 2026-09-30, поле ``publish_time`` у ``post_draft`` и у
``post_draft/publish/``). Черновик у блога один: любой режим перезаписывает то,
что автор держит в редакторе.

Авторизация — Bearer из auth.json (см. :mod:`boosty_auth`). Истёкший токен клиент
обновляет сам: заранее, если до истечения меньше десяти минут, и один раз по
401. Если refresh не помог, поднимается :class:`boosty_auth.BoostyAuthError` — это
PermanentError, publisher не повторяет шаг и сразу сообщает админу, что
делать.

HTTP спрятан за :class:`Transport`: в проде это aiohttp, в тестах — фейк.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import aiohttp
from boosty_auth import DEFAULT_USER_AGENT, AuthData, BoostyAuthError, load, save
from content import build_audio_block, build_post_data, build_teaser_data
from loguru import logger
from sagenza_tgbot_sdk.resilience import PermanentError

# Фиксированные хосты internal API. Не конфиг: если Boosty их переедет,
# ломается весь протокол, а не одна настройка.
API_URL = "https://api.boosty.to"
UPLOAD_URL = "https://upload.boosty.to"
_CHUNK = 5 * 1024 * 1024  # 5 МБ — размер чанка, как у веб-редактора
# Заголовки, которые редактор шлёт к Boosty-эндпоинтам помимо Bearer.
_BOOSTY_HEADERS = {"X-App": "web", "X-Locale": "ru_RU", "X-Currency": "RUB"}
_TIMEOUT = aiohttp.ClientTimeout(total=300)


@dataclass
class Response:
    status: int
    body: bytes

    def json(self):
        if not self.body:
            return {}
        try:
            return json.loads(self.body)
        except ValueError:
            return {"raw": self.body[:500].decode("utf-8", errors="replace")}


class Transport(Protocol):
    async def send(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        data: dict | bytes | None = None,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> Response: ...


class AiohttpTransport:
    """Боевой транспорт: одна aiohttp-сессия на сервис."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def send(self, method, url, *, headers, data=None, json_body=None, params=None) -> Response:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=_TIMEOUT)
        async with self._session.request(
            method, url, headers=headers, data=data, json=json_body, params=params
        ) as resp:
            return Response(resp.status, await resp.read())

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()


class BoostyApiError(RuntimeError):
    """Boosty ответил ошибкой (не авторизации) — шаг можно повторить."""

    def __init__(self, what: str, response: Response) -> None:
        super().__init__(f"Boosty {what} → HTTP {response.status}: {response.json()!r}")
        self.status = response.status


class BoostyPublishedNowError(PermanentError):
    """Отложенный пост ушёл подписчикам сразу: Boosty не принял ``publish_time``.

    PermanentError: повтор шага опубликовал бы второй пост.
    """

    def __init__(self, post_id: str) -> None:
        super().__init__(f"Boosty опубликовал пост {post_id or '?'} сразу вместо отложенной публикации")
        self.post_id = post_id


@dataclass
class PostContent:
    """Содержимое поста: текст, загруженные аудио и обложка, доступ."""

    title: str
    body: str
    chapters: list[list[str]] | None
    audio_id: str
    audio_size: int
    audio_title: str
    cover_id: str
    subscription_level_id: str
    price: int
    advertiser_info: str = ""


def _post_id(post: dict) -> str:
    return str(post.get("id") or post.get("int_id") or "")


class BoostyClient:
    """Stateful-обёртка: один блог, токены из auth_file."""

    def __init__(self, blog_name: str, auth_file: str, transport: Transport | None = None) -> None:
        # Пустой blog_name допустим при конструировании (импорт модуля при
        # незаданном BOOSTY_BLOG не должен падать); проверяем в ensure_auth.
        self.blog_name = blog_name
        self.auth_file = auth_file
        self.transport: Transport = transport or AiohttpTransport()
        self._auth: AuthData | None = None
        self._refresh_lock = asyncio.Lock()

    async def ensure_auth(self) -> None:
        """Грузит токены из файла и обновляет их, если скоро истекут."""
        if not self.blog_name:
            raise BoostyAuthError("BOOSTY_BLOG не задан")
        if self._auth is None:
            self._auth = await asyncio.to_thread(load, self.auth_file)
            logger.debug(f"Boosty auth loaded for blog '{self.blog_name}'")
        if self._auth.expires_soon():
            await self.refresh()

    async def refresh(self) -> None:
        """Обменивает refresh_token на новую пару и пересохраняет файл."""
        if self._auth is None:
            self._auth = await asyncio.to_thread(load, self.auth_file)
        async with self._refresh_lock:
            auth = self._auth
            resp = await self.transport.send(
                "POST",
                f"{API_URL}/oauth/token/",
                headers=self._headers(authorized=False),
                data={
                    "device_id": auth.device_id,
                    "device_os": "web",
                    "grant_type": "refresh_token",
                    "refresh_token": auth.refresh_token,
                },
            )
            if resp.status in (400, 401, 403):
                raise BoostyAuthError(f"refresh_token отклонён (HTTP {resp.status}: {resp.json()!r})")
            if resp.status >= 400:
                raise BoostyApiError("refresh", resp)
            auth.apply_refresh(resp.json())
            await asyncio.to_thread(save, self.auth_file, auth)
        logger.info("Boosty access token refreshed")

    def _headers(self, extra: dict | None = None, *, authorized: bool = True) -> dict[str, str]:
        auth = self._auth
        headers = {"User-Agent": (auth.user_agent if auth else None) or DEFAULT_USER_AGENT, **_BOOSTY_HEADERS}
        if authorized and auth and auth.access_token:
            headers["Authorization"] = f"Bearer {auth.access_token}"
        if extra:
            headers.update(extra)
        return headers

    async def _call(
        self, what: str, method: str, url: str, *, extra_headers: dict | None = None, **kwargs
    ) -> Response:
        """Запрос с одним refresh по 401; ошибки → BoostyAuthError/BoostyApiError."""
        await self.ensure_auth()
        resp = await self.transport.send(method, url, headers=self._headers(extra_headers), **kwargs)
        if resp.status == 401:
            logger.warning(f"Boosty {what}: 401, обновляю токен")
            await self.refresh()
            resp = await self.transport.send(method, url, headers=self._headers(extra_headers), **kwargs)
            if resp.status == 401:
                raise BoostyAuthError(f"{what}: 401 даже после refresh")
        if resp.status == 403:
            raise BoostyAuthError(f"{what}: 403 — у аккаунта нет прав на блог {self.blog_name}")
        if resp.status >= 400:
            raise BoostyApiError(what, resp)
        return resp

    async def _api_json(self, what: str, method: str, path: str, **kwargs) -> dict:
        resp = await self._call(what, method, f"{API_URL}{path}", **kwargs)
        body = resp.json()
        return body if isinstance(body, dict) else {"data": body}

    async def get_container_id(self) -> int:
        """ownerId блога — он же `container_id` для upload аудио.

        Фоллбэк, если BOOSTY_OWNER_ID не задан в конфиге. Черновик существует
        только когда он создан/сохранён в редакторе — на «пустом» блоге
        `postDraft` == null, тогда нужен BOOSTY_OWNER_ID.
        """
        draft = await self.get_draft()
        owner_id = draft.get("ownerId") if draft else None
        if owner_id is None:
            raise RuntimeError(
                "Cannot resolve ownerId: no active post_draft on the blog. "
                "Set BOOSTY_OWNER_ID in config (numeric blog owner id)."
            )
        return int(owner_id)

    async def get_blog(self) -> dict:
        """Карточка блога: проверяет, что токен видит блог (для смоука)."""
        return await self._api_json("blog", "GET", f"/v1/blog/{self.blog_name}")

    async def get_subscription_levels(self) -> list[dict]:
        """Уровни подписки блога (id нужен для BOOSTY_SUBSCRIPTION_LEVEL_ID)."""
        resp = await self._api_json(
            "subscription_level",
            "GET",
            f"/v1/blog/{self.blog_name}/subscription_level/",
            params={"show_free_level": "true"},
        )
        data = resp.get("data")
        return data if isinstance(data, list) else []

    async def get_post(self, post_id: str) -> dict:
        """Пост по id — так publisher проверяет, что публикация состоялась."""
        resp = await self._api_json("get_post", "GET", f"/v1/blog/{self.blog_name}/post/{post_id}")
        return resp.get("data", resp) if isinstance(resp.get("data"), dict) else resp

    async def _upload(self, kind: str, init_body: dict, path: str) -> str:
        """Общий chunked-upload: init → чанки → complete. Возвращает fileId."""
        init = await self._call(f"upload {kind} init", "POST", f"{UPLOAD_URL}/{kind}", json_body=init_body)
        file_id = init.json().get("fileId")
        if not file_id:
            raise RuntimeError(f"No fileId in upload-init response: {init.json()!r}")

        content = await asyncio.to_thread(Path(path).read_bytes)
        # Чанки нумеруются заголовком X-PartNumber (1-based) — без него 400.
        for part, offset in enumerate(range(0, len(content), _CHUNK), start=1):
            await self._call(
                f"upload {kind} part {part}",
                "POST",
                f"{UPLOAD_URL}/upload/{file_id}",
                data=content[offset : offset + _CHUNK],
                extra_headers={"Content-Type": "application/octet-stream", "X-PartNumber": str(part)},
            )
        await self._call(f"upload {kind} complete", "POST", f"{UPLOAD_URL}/upload/{file_id}/complete")

        logger.debug(f"Boosty upload complete: {file_id} ({len(content)} bytes)")
        return file_id

    async def upload_audio(self, path: str, container_id: int) -> tuple[str, int]:
        """Загружает mp3. Возвращает (fileId, size_bytes)."""
        file_id = await self._upload("audio", {"container_id": container_id, "container_type": "post_draft"}, path)
        return file_id, Path(path).stat().st_size

    async def upload_image(self, path: str) -> str:
        """Загружает обложку. Возвращает fileId."""
        return await self._upload("image", {}, path)

    async def save_draft(self, post: PostContent, *, publish_time: int | None = None) -> None:
        """Заполняет черновик-синглтон блога (``PUT post_draft``), ничего не публикуя.

        Этот же запрос редактор шлёт автосейвом, пока автор печатает.
        ``publish_time`` — время отложенной публикации (unix, секунды).
        """
        payload = {
            "title": post.title,
            "data": build_post_data(
                post.body, post.chapters, audio=build_audio_block(post.audio_id, post.audio_size, post.audio_title)
            ),
            "teaser_data": build_teaser_data(post.cover_id, post.body),
            "subscription_level_id": str(post.subscription_level_id),
            "price": str(post.price),
            "tags": "",
            "deny_comments": "false",
            "deny_reactions": "false",
            "wait_video": "false",
            "advertiser_info": post.advertiser_info,
            "last_updated_at": str(int(time.time())),
            "bundle_ids": "",
        }
        if publish_time is not None:
            payload["publish_time"] = str(publish_time)
        await self._api_json("save draft", "PUT", f"/v1/blog/{self.blog_name}/post_draft", data=payload)

    async def get_draft(self) -> dict | None:
        """Черновик блога (``data.postDraft``) или None, если его нет."""
        resp = await self._api_json("post_draft", "GET", f"/v1/blog/{self.blog_name}/post_draft")
        data = resp.get("data")
        draft = data.get("postDraft") if isinstance(data, dict) else None
        return draft if isinstance(draft, dict) else None

    async def _publish_draft(self, form: dict[str, str]) -> dict:
        resp = await self._api_json("publish", "POST", f"/v1/blog/{self.blog_name}/post_draft/publish/", data=form)
        data_obj = resp.get("data")
        post = data_obj.get("post") if isinstance(data_obj, dict) else None
        return post if isinstance(post, dict) else {}

    async def publish(self, post: PostContent) -> str:
        """Публикует пост сразу. Возвращает id поста (uuid из ``data.post.id``).

        Два шага (сверено с HAR клика «Опубликовать»): заполнить черновик и
        ``POST post_draft/publish/``.
        """
        await self.save_draft(post)
        published = await self._publish_draft({"is_showcase_visible": "true"})
        post_id = _post_id(published)
        logger.success(f"Boosty post published (id={post_id or '?'})")
        return post_id

    async def schedule(self, post: PostContent, publish_time: int, *, showcase: bool = True) -> dict:
        """Создаёт отложенный пост: он появится у подписчиков в ``publish_time``.

        Возвращает пост из ответа. Если Boosty проигнорировал время и
        опубликовал пост сразу, поднимает :class:`BoostyPublishedNowError`:
        пост уже виден, повторять шаг нельзя. ``showcase=False`` не выводит
        пост на витрину блога, где видна карточка «ещё не опубликован».
        """
        if publish_time <= time.time():
            raise ValueError("publish_time must be in the future")
        await self.save_draft(post, publish_time=publish_time)
        visible = "true" if showcase else "false"
        scheduled = await self._publish_draft({"publish_time": str(publish_time), "is_showcase_visible": visible})
        if scheduled.get("isPublished"):
            raise BoostyPublishedNowError(_post_id(scheduled))
        logger.success(f"Boosty post scheduled (id={_post_id(scheduled) or '?'}, publish_time={publish_time})")
        return scheduled

    async def delete_post(self, post_id: str) -> None:
        """Удаляет пост блога (``DELETE /v1/blog/{blog}/post/{id}``)."""
        await self._api_json("delete_post", "DELETE", f"/v1/blog/{self.blog_name}/post/{post_id}")

    async def close(self) -> None:
        close = getattr(self.transport, "close", None)
        if close is not None:
            await close()
