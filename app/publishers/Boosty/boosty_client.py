"""Клиент Boosty: многошаговый upload+publish-флоу, реверснутый из трафика
редактора (см. `.planning/spikes/boosty-sponsr-feasibility.md`,
«Verified upload+publish flow»).

Последовательность публикации:

    GET  api.boosty.to/v1/blog/{blog}/post_draft        → ownerId (= container_id)
    POST upload.boosty.to/audio {container_id,...}       → fileId
    POST upload.boosty.to/upload/{fileId}  (octet, чанки 5 МБ)
    POST upload.boosty.to/upload/{fileId}/complete
    POST upload.boosty.to/image {}                       → fileId  (обложка)
    POST upload.boosty.to/upload/{fileId} (+/complete)
    POST api.boosty.to/v1/blog/{blog}/post/              → опубликованный пост

Два хоста:
* `api.boosty.to` — через `API.request` либы (Bearer + авто-refresh по 401);
* `upload.boosty.to` — другой хост, `API.request` туда не умеет (он прибит к
  `API_URL`), поэтому бьём его же `http_client` напрямую с теми же заголовками
  (Bearer из `auth.headers`) + X-App/X-Locale/X-Currency.

Auth-bootstrap: один раз вручную логинимся в браузере, экспортируем `auth.json`
(access/refresh/device_id) в `BOOSTY_AUTH_FILE`. `FileAuthDataResolver` его
читает/перезаписывает; refresh — `auth.refresh_auth_data` (по 401 автоматически
внутри либы + наш ежечасный прогрев, см. main.py).

Bearer на `upload.boosty.to` подтверждён живым прогоном (init /audio отдаёт
fileId). Чанки обязаны нести заголовок `X-PartNumber` (1-based) — без него 400.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from content import build_audio_block, build_post_data, build_teaser_data
from loguru import logger

# Импорт либы изолирован: при отсутствии пакета (unit-окружение без boosty)
# модуль всё равно импортируется, ошибка всплывёт при построении клиента.
try:
    from boosty.api import API
    from boosty.api.api import API_URL
    from boosty.api.auth import Auth
    from boosty.api.auth.resolvers.file import FileAuthDataResolver

    _IMPORT_ERROR: Exception | None = None
except Exception as e:  # pragma: no cover - зависит от окружения
    API = Auth = FileAuthDataResolver = None  # type: ignore[assignment]
    API_URL = "https://api.boosty.to"
    _IMPORT_ERROR = e

UPLOAD_URL = "https://upload.boosty.to"
_CHUNK = 5 * 1024 * 1024  # 5 МБ — размер чанка, как у веб-редактора
# Заголовки, которые редактор шлёт к Boosty-эндпоинтам помимо Bearer.
_BOOSTY_HEADERS = {"X-App": "web", "X-Locale": "ru_RU", "X-Currency": "RUB"}


class BoostyClient:
    """Stateful-обёртка: один блог, ленивое построение API."""

    def __init__(self, blog_name: str, auth_file: str) -> None:
        # Пустой blog_name допустим при конструировании (импорт модуля при
        # незаданном BOOSTY_BLOG не должен падать); проверяем в ensure_auth.
        self.blog_name = blog_name
        self.auth_file = auth_file
        self._api: API | None = None  # type: ignore[valid-type]

    async def ensure_auth(self) -> None:
        """Строит API из auth.json (blocking IO → to_thread) и валидирует токен.

        Идемпотентно. Refresh по 401 делает сама либа в `API.request`; здесь —
        начальная загрузка + понятная ошибка, если файл с токеном не готов.
        """
        if self._api is not None:
            return
        if not self.blog_name:
            raise RuntimeError("BOOSTY_BLOG is not configured")
        if _IMPORT_ERROR is not None:
            raise RuntimeError(f"boosty library is not available: {_IMPORT_ERROR!r}")

        def _build() -> API:  # type: ignore[valid-type]
            return API(auth=Auth(FileAuthDataResolver(auth_file=self.auth_file)))

        api = await asyncio.to_thread(_build)
        if not getattr(api.auth.auth_data, "access_token", None):
            raise RuntimeError(
                f"No access_token in {self.auth_file}. Export auth.json from a "
                "browser session (access_token/refresh_token/device_id)."
            )
        self._api = api
        logger.debug(f"Boosty auth loaded for blog '{self.blog_name}'")

    async def refresh(self) -> None:
        """Принудительный refresh токена (для ежечасного прогрева сессии)."""
        await self.ensure_auth()
        assert self._api is not None
        await self._api.auth.refresh_auth_data(self._api.http_client, API_URL)
        logger.debug("Boosty access token refreshed")

    def _headers(self, extra: dict | None = None) -> dict:
        """Bearer + UA (из либы) + X-App/X-Locale/X-Currency (+ extra)."""
        assert self._api is not None
        headers = dict(self._api.auth.headers)
        headers.update(_BOOSTY_HEADERS)
        if extra:
            headers.update(extra)
        return headers

    async def get_container_id(self) -> int:
        """ownerId блога — он же `container_id` для upload аудио.

        Фоллбэк, если BOOSTY_OWNER_ID не задан в конфиге: пытаемся достать
        ownerId из активного черновика. НО черновик существует только когда он
        создан/сохранён в редакторе — на «пустом» блоге `postDraft` == null.
        В этом случае задай BOOSTY_OWNER_ID явно (числовой id владельца блога).
        """
        await self.ensure_auth()
        assert self._api is not None
        resp = await self._api.request("GET", f"/v1/blog/{self.blog_name}/post_draft")
        data = resp.get("data") if isinstance(resp, dict) else None
        draft = data.get("postDraft") if isinstance(data, dict) else None
        owner_id = draft.get("ownerId") if isinstance(draft, dict) else None
        if owner_id is None:
            raise RuntimeError(
                "Cannot resolve ownerId: no active post_draft on the blog. "
                "Set BOOSTY_OWNER_ID in config (numeric blog owner id). "
                f"Raw response: {resp!r}"
            )
        return int(owner_id)

    async def _upload(self, init_url: str, init_body: dict, path: str) -> str:
        """Общий chunked-upload: init → чанки → complete. Возвращает fileId."""
        await self.ensure_auth()
        assert self._api is not None
        client = self._api.http_client

        init = await client.request_json(init_url, method="POST", json=init_body, headers=self._headers())
        file_id = init.get("fileId")
        if not file_id:
            raise RuntimeError(f"No fileId in upload-init response: {init!r}")

        content = await asyncio.to_thread(Path(path).read_bytes)
        # Чанки нумеруются заголовком X-PartNumber (1-based) — без него 400.
        for part, offset in enumerate(range(0, len(content), _CHUNK), start=1):
            chunk = content[offset : offset + _CHUNK]
            headers = self._headers({"Content-Type": "application/octet-stream", "X-PartNumber": str(part)})
            resp = await client.request_raw(
                f"{UPLOAD_URL}/upload/{file_id}", method="POST", data=chunk, headers=headers
            )
            if resp.status >= 400:
                raise RuntimeError(f"Boosty chunk upload failed ({resp.status}, part {part}) for {file_id}")

        done = await client.request_raw(
            f"{UPLOAD_URL}/upload/{file_id}/complete", method="POST", headers=self._headers()
        )
        if done.status >= 400:
            raise RuntimeError(f"Boosty upload complete failed ({done.status}) for {file_id}")

        logger.debug(f"Boosty upload complete: {file_id} ({len(content)} bytes)")
        return file_id

    async def upload_audio(self, path: str, container_id: int) -> tuple[str, int]:
        """Загружает mp3. Возвращает (fileId, size_bytes)."""
        file_id = await self._upload(
            f"{UPLOAD_URL}/audio",
            {"container_id": container_id, "container_type": "post_draft"},
            path,
        )
        return file_id, Path(path).stat().st_size

    async def upload_image(self, path: str) -> str:
        """Загружает обложку. Возвращает fileId."""
        return await self._upload(f"{UPLOAD_URL}/image", {}, path)

    async def publish(
        self,
        *,
        title: str,
        body: str,
        chapters: list[list[str]] | None,
        audio_id: str,
        audio_size: int,
        audio_title: str,
        cover_id: str,
        subscription_level_id: str,
        price: int,
        advertiser_info: str = "",
    ) -> str:
        """Публикует пост с прикреплённым аудио и обложкой-тизером.

        Два шага (сверено с HAR клика «Опубликовать»):
          1. PUT  /v1/blog/{blog}/post_draft         — заполнить черновик-синглтон;
          2. POST /v1/blog/{blog}/post_draft/publish/ — опубликовать (body
             `is_showcase_visible=true`). Возвращает опубликованный пост.
        Возвращает id поста (uuid из `data.post.id`).
        """
        await self.ensure_auth()
        assert self._api is not None

        data = build_post_data(body, chapters, audio=build_audio_block(audio_id, audio_size, audio_title))
        teaser = build_teaser_data(cover_id, body)

        payload = {
            "title": title,
            "data": data,
            "teaser_data": teaser,
            "subscription_level_id": str(subscription_level_id),
            "price": str(price),
            "tags": "",
            "deny_comments": "false",
            "deny_reactions": "false",
            "wait_video": "false",
            "advertiser_info": advertiser_info,
            "last_updated_at": str(int(time.time())),
            "bundle_ids": "",
        }
        await self._api.request("PUT", f"/v1/blog/{self.blog_name}/post_draft", data=payload)

        resp = await self._api.request(
            "POST",
            f"/v1/blog/{self.blog_name}/post_draft/publish/",
            data={"is_showcase_visible": "true"},
        )
        data_obj = resp.get("data") if isinstance(resp, dict) else None
        post = data_obj.get("post") if isinstance(data_obj, dict) else None
        post_id = str(post.get("id") or post.get("int_id") or "") if isinstance(post, dict) else ""
        logger.success(f"Boosty post published (id={post_id or '?'})")
        return post_id
