"""Клиент Sponsr: публикация поста с аудио так, как это делает веб-редактор.

Лестница интеграции и где мы на ней:

1. Официального API у Sponsr нет (ни для чтения, ни для публикации).
2. **Выбран этот уровень**: HTTP-запросы веб-редактора (httpx) с кукой
   ``SESS``, как у открытого клиента idlesign/sponsrdump. Запросы сверены с
   записью редактора 25.10.2026 (пост с mp3 для подписчиков уровня).
3. Camoufox (браузер): если редактор начнёт требовать JS-подписи запросов.

Шаги публикации (как в редакторе):

    GET  /<slug>/manage/post/new/                   → id проекта, уровень подписки
    GET  /project/<id>/manage/resumable-file/?...   → file_id, status=UPLOAD
    POST /project/<id>/manage/resumable-file/       multipart, куски по 5 МБ
    POST .../upload-file-info/update-chunk-file     после каждого куска
    POST .../upload-file-info/complete-file         {file_id, file_category=podcast}
    GET  .../file-state/?file_id=                   → ждём file_upload_state=completed
    POST .../upload-file-info/update-file-state     {file_id}
    POST .../post-save/new                          поля формы редактора, level_id = замок
    GET  /api/v2/content/posts/?project_id=         → проверка, что пост появился
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
from loguru import logger
from sagenza_tgbot_sdk.masking import register_secrets
from sagenza_tgbot_sdk.resilience import PermanentError

BASE_URL = "https://sponsr.ru"
_TIMEOUT = httpx.Timeout(60.0, read=600.0, write=600.0)
# Размер куска, которым грузит редактор (Ve в bundle-manage.js).
CHUNK_SIZE = 5 * 1024 * 1024
_AJAX = {"X-Requested-With": "XMLHttpRequest", "Origin": BASE_URL}
# Ajax.postJSON редактора добавляет к запросам заголовок ``e: true``.
_EDITOR = {**_AJAX, "e": "true"}
_MSK = timezone(timedelta(hours=3))
_FILE_STATE_ATTEMPTS = 60
_PROJECT_ID_RES = (
    re.compile(r'js-toggle-project-offline"\s+data-id="(\d+)"'),
    re.compile(r'project-statuses-modal-(\d+)"'),
    re.compile(r"/images/projects/\d+/(\d+)/"),
)
_LEVEL_SELECT_RE = re.compile(r'<select[^>]*name="level_id"[^>]*>(.*?)</select>', re.S)
_SELECTED_LEVEL_RE = re.compile(r'<option value="(\d+)"\s+selected')
_UNSAFE_NAME_RE = re.compile(r"[^a-zа-я0-9._\-\s]", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


class SponsrAuthError(PermanentError):
    HINT = (
        "Обновите secrets/sponsr/sponsr_session.json: войдите на sponsr.ru и выполните "
        "`python smoke.py import-cookie` (см. app/publishers/Sponsr/SMOKE.md)."
    )

    def __init__(self, reason: str) -> None:
        super().__init__(f"Sponsr: {reason}. {self.HINT}")


class SponsrApiError(RuntimeError):
    pass


def load_session(path: str) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise SponsrAuthError(f"нет файла сессии {path}") from e
    except ValueError as e:
        raise SponsrAuthError(f"файл сессии {path} повреждён") from e
    if not isinstance(raw, dict) or not raw.get("SESS"):
        raise SponsrAuthError(f"в {path} нет куки SESS")
    # Кука сессии не должна попасть в логи и в текст ошибки, который уходит боту.
    register_secrets(str(raw["SESS"]))
    return raw


def save_session(path: str, sess: str, user_agent: str | None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"SESS": sess.strip(), "user_agent": user_agent}), encoding="utf-8")


def parse_editor_page(html: str) -> tuple[str | None, str | None]:
    """id проекта и уровень подписки, выбранный в редакторе по умолчанию."""
    project_id = next((m.group(1) for regex in _PROJECT_ID_RES if (m := regex.search(html))), None)
    level_id = None
    select = _LEVEL_SELECT_RE.search(html)
    if select:
        selected = _SELECTED_LEVEL_RE.search(select.group(1))
        level_id = selected.group(1) if selected else None
    return project_id, level_id


def safe_file_name(name: str) -> str:
    """Имя файла, очищенное так же, как это делает редактор перед загрузкой."""
    return _UNSAFE_NAME_RE.sub("", name)


def reading_seconds(html: str) -> int:
    """post_duration_text: в записи редактора это длина текста / 90."""
    return round(len(_TAG_RE.sub("", html)) / 90)


class SponsrClient:
    def __init__(
        self,
        session_file: str,
        project: str | None,
        level_id: str | None = None,
        http: httpx.AsyncClient | None = None,
        poll_delay: float = 2.0,
    ) -> None:
        self.session_file = session_file
        self.project = project
        self.level_id = level_id
        self.project_id: str | None = None
        self._http = http
        self.poll_delay = poll_delay

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            session = await asyncio.to_thread(load_session, self.session_file)
            self._http = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=_TIMEOUT,
                headers={"User-Agent": session.get("user_agent") or "Mozilla/5.0"},
                cookies={"SESS": session["SESS"]},
                follow_redirects=False,
            )
        return self._http

    async def _json(self, what: str, method: str, url: str, **kwargs) -> dict:
        http = await self._client()
        resp = await http.request(method, url, **kwargs)
        location = resp.headers.get("location", "")
        if resp.status_code in (401, 403) or 300 <= resp.status_code < 400:
            raise SponsrAuthError(f"{what}: сессия не принята (HTTP {resp.status_code} {location})")
        if resp.status_code >= 400:
            raise SponsrApiError(f"Sponsr {what} → HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            body = resp.json()
        except ValueError as e:
            raise SponsrApiError(f"Sponsr {what}: ответ не JSON: {resp.text[:300]}") from e
        if isinstance(body, dict) and body.get("error"):
            raise SponsrApiError(f"Sponsr {what}: {body['error']}")
        return body

    async def ensure_auth(self) -> str:
        """Открывает редактор поста: кука должна давать кабинет автора. Возвращает id проекта."""
        if self.project_id:
            return self.project_id
        if not self.project:
            raise SponsrAuthError("SPONSR_PROJECT не задан")
        http = await self._client()
        resp = await http.get(f"/{self.project}/manage/post/new/")
        location = resp.headers.get("location", "")
        if resp.status_code in (401, 403) or 300 <= resp.status_code < 400:
            raise SponsrAuthError(f"редактор не открылся (HTTP {resp.status_code} {location})")
        if resp.status_code >= 400:
            raise RuntimeError(f"Sponsr editor page → HTTP {resp.status_code}")
        project_id, level_id = parse_editor_page(resp.text)
        if not project_id:
            raise SponsrAuthError("на странице редактора нет id проекта, это не кабинет автора")
        self.project_id = project_id
        self.level_id = self.level_id or level_id
        return project_id

    async def upload_audio(self, path: str) -> tuple[str, int]:
        """Грузит mp3 кусками, как редактор. Возвращает (file_id, длительность в секундах)."""
        project_id = await self.ensure_auth()
        base = f"/project/{project_id}/manage"
        file = Path(path)
        data = await asyncio.to_thread(file.read_bytes)
        size = len(data)
        name = safe_file_name(file.name)
        meta = {
            "file_name": file.name,
            "file_size": str(size),
            "file_upload_uid": f"{project_id}_{size}_{name}",
            "file_type": "audio/mpeg",
            "file_category": "podcast",
        }
        upload_id = f"upload_{int(time.time() * 1000)}_{random.random()}"
        start = await self._json(
            "start upload",
            "GET",
            f"{base}/resumable-file/",
            params={**meta, "post_id": "", "uploadId": upload_id},
            headers=_AJAX,
        )
        state = start.get("response") or {}
        if state.get("status") != "UPLOAD" or not state.get("file_id"):
            raise SponsrApiError(f"Sponsr start upload: неожиданный ответ {state}")
        file_id = str(state["file_id"])
        meta["file_name"] = state.get("file_name") or file.name
        offset = int(state.get("last_byte") or 0)
        while offset < size:
            end = min(offset + CHUNK_SIZE, size)
            fields = {
                **meta,
                "post_id": "null",
                "chunk_size": str(end - offset),
                "completed": "1" if end == size else "0",
                "last_byte": str(end),
                "file_id": file_id,
            }
            chunk = await self._json(
                "upload chunk",
                "POST",
                f"{base}/resumable-file/",
                data=fields,
                files={"file": ("blob", data[offset:end], "application/octet-stream")},
                headers=_AJAX,
            )
            part = chunk.get("response") or {}
            await self._json(
                "update chunk",
                "POST",
                f"{base}/upload-file-info/update-chunk-file",
                data={k: str(part.get(k, "")) for k in ("file_upload_uid", "last_byte", "completed", "file_hash")},
                headers=_EDITOR,
            )
            offset = int(part.get("last_byte") or end)
        await self._json(
            "complete file",
            "POST",
            f"{base}/upload-file-info/complete-file",
            data={"file_id": file_id, "file_category": "podcast"},
            headers=_EDITOR,
        )
        duration = await self._wait_file(base, file_id)
        await self._json(
            "update file state",
            "POST",
            f"{base}/upload-file-info/update-file-state",
            data={"file_id": file_id},
            headers=_EDITOR,
        )
        return file_id, duration

    async def _wait_file(self, base: str, file_id: str) -> int:
        upload_state = None
        for _ in range(_FILE_STATE_ATTEMPTS):
            body = await self._json(
                "file state", "GET", f"{base}/file-state/", params={"file_id": file_id}, headers=_EDITOR
            )
            info = body.get("response") or {}
            upload_state = info.get("file_upload_state")
            if upload_state == "completed":
                return round(float(info.get("file_duration") or 0))
            if upload_state == "failed":
                raise PermanentError("Sponsr: файл не обработан (file_upload_state=failed)")
            await asyncio.sleep(self.poll_delay)
        raise RuntimeError(f"Sponsr file {file_id} не обработан (state={upload_state})")

    async def save_post(self, *, title: str, content: str, teaser: str, file_id: str, duration: int) -> str:
        """Публикует пост для подписчиков уровня. Возвращает id поста."""
        project_id = await self.ensure_auth()
        if not self.level_id:
            raise PermanentError("Sponsr: уровень подписки не найден, задайте SPONSR_LEVEL_ID")
        form = {
            "post_id": "",
            "project_id": project_id,
            "level_id": self.level_id,
            "post_text": content,
            "post_title": title,
            "post_teaser": teaser,
            "meta_title": "",
            "meta_description": "",
            "post_rss_teaser": "",
            "post_date": datetime.now(UTC).astimezone(_MSK).strftime("%Y-%m-%d %H:%M:%S"),
            "post_pinned": "0",
            "post_notified": "0",
            "post_extended_view": "0",
            "set_def_level": "0",
            "post_access_type": "def",
            "post_access_value": "0",
            "post_image": "",
            "post_file": "",
            "media_file": file_id,
            "post_status": "active",
            "post_duration_podcast": str(duration),
            "post_duration_text": str(reading_seconds(content)),
            "post_duration_video": "0",
        }
        body = await self._json(
            "save post", "POST", f"/project/{project_id}/manage/post-save/new", data=form, headers=_EDITOR
        )
        post_id = (body.get("response") or {}).get("post_id")
        if not post_id:
            raise SponsrApiError(f"Sponsr save post: нет post_id в ответе {body}")
        logger.success(f"Sponsr post published (id={post_id})")
        return str(post_id)

    async def publish(self, *, title: str, content: str, teaser: str, path: str) -> str:
        """Пост с аудио для подписчиков. Возвращает id поста."""
        file_id, duration = await self.upload_audio(path)
        return await self.save_post(title=title, content=content, teaser=teaser, file_id=file_id, duration=duration)

    async def get_post(self, post_id: str) -> dict | None:
        project_id = await self.ensure_auth()
        body = await self._json(
            "posts",
            "GET",
            "/api/v2/content/posts/",
            params={"project_id": project_id, "limit": "20", "page": "1", "orderBy": "date", "orderByType": "desc"},
        )
        return next((item for item in body.get("list") or [] if str(item.get("id")) == str(post_id)), None)

    def post_url(self, post_id: str) -> str:
        return f"{BASE_URL}/{self.project}/{post_id}/"

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
