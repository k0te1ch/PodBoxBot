"""Клиент Sponsr: сессия веб-редактора по куке SESS.

Лестница интеграции и где мы на ней:

1. Официального API у Sponsr нет (ни для чтения, ни для публикации; на
   2026 год раздела для разработчиков не существует).
2. **Выбран этот уровень** — HTTP-запросы веб-редактора (httpx) с кукой
   ``SESS``, как у открытого клиента idlesign/sponsrdump. Сессия и проверка
   входа реализованы. Сами запросы публикации нигде не описаны, а доступа к
   кабинету автора нет, поэтому они не придуманы наугад: их снимают из HAR
   ручной публикации (``smoke.py har``) и дописывают в :meth:`publish`.
   До этого publisher честно отвечает ошибкой ``SponsrNotCalibratedError``.
3. Camoufox (браузер) — если редактор окажется недоступен без JS или
   запросы подписываются в браузере. Решается по тому же HAR.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from sagenza_tgbot_sdk.resilience import PermanentError

BASE_URL = "https://sponsr.ru"
_TIMEOUT = httpx.Timeout(60.0, read=600.0, write=600.0)


class SponsrAuthError(PermanentError):
    HINT = (
        "Обновите secrets/sponsr/sponsr_session.json: войдите на sponsr.ru и выполните "
        "`python smoke.py import-cookie` (см. app/publishers/Sponsr/SMOKE.md)."
    )

    def __init__(self, reason: str) -> None:
        super().__init__(f"Sponsr: {reason}. {self.HINT}")


class SponsrNotCalibratedError(PermanentError):
    def __init__(self) -> None:
        super().__init__(
            "Sponsr: запросы публикации ещё не сняты с редактора. Опубликуйте пост вручную "
            "с записью HAR и прогоните `python smoke.py har <файл>` (см. app/publishers/Sponsr/SMOKE.md)."
        )


def load_session(path: str) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise SponsrAuthError(f"нет файла сессии {path}") from e
    except ValueError as e:
        raise SponsrAuthError(f"файл сессии {path} повреждён") from e
    if not isinstance(raw, dict) or not raw.get("SESS"):
        raise SponsrAuthError(f"в {path} нет куки SESS")
    return raw


def save_session(path: str, sess: str, user_agent: str | None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"SESS": sess.strip(), "user_agent": user_agent}), encoding="utf-8")


class SponsrClient:
    def __init__(self, session_file: str, project: str | None, http: httpx.AsyncClient | None = None) -> None:
        self.session_file = session_file
        self.project = project
        self._http = http

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

    async def ensure_auth(self) -> None:
        """Проверяет, что кука открывает кабинет автора, а не страницу входа."""
        if not self.project:
            raise SponsrAuthError("SPONSR_PROJECT не задан")
        http = await self._client()
        resp = await http.get(f"/{self.project}/")
        location = resp.headers.get("location", "")
        if resp.status_code in (401, 403) or (300 <= resp.status_code < 400 and "auth" in location):
            raise SponsrAuthError(f"сессия не принята (HTTP {resp.status_code} {location})")
        if resp.status_code >= 400:
            raise RuntimeError(f"Sponsr project page → HTTP {resp.status_code}")

    async def publish(self, *, title: str, content: str, path: str) -> str:
        """Публикация поста с аудио для подписчиков. Возвращает id поста."""
        raise SponsrNotCalibratedError

    async def get_post(self, post_id: str) -> dict | None:
        http = await self._client()
        resp = await http.get(f"/{self.project}/{post_id}/")
        return {"id": post_id} if resp.status_code == 200 else None

    def post_url(self, post_id: str) -> str:
        return f"{BASE_URL}/{self.project}/{post_id}/"

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
