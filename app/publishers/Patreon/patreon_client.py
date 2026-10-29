"""Клиент Patreon: создание поста так, как это делает веб-редактор.

Лестница интеграции и где мы на ней:

1. Официальный API v2 постов не создаёт: там есть только чтение кампаний,
   уровней, участников и постов плюс вебхуки. Для публикации он не годится.
2. **Выбран этот уровень**: HTTP-запросы веб-приложения patreon.com (httpx),
   сессионная кука ``session_id``, CSRF-подпись, JSON:API. Последовательность
   сверена с записью редактора 25.10.2026 (аудиопост для платных патронов).
3. Если Cloudflare перед patreon.com начнёт отбивать httpx (403 с
   челленджем), следующий шаг: браузер Camoufox с той же кукой; интерфейс
   ``PatreonClient`` для publisher'а при этом не меняется.

Шаги публикации (как в редакторе):

    GET   /REST/auth/CSRFTicket?uri=/                        → {token}: X-CSRF-Signature
    GET   /api/current_user?include=campaign                 → id кампании
    GET   /api/campaigns/{id}?include=access_rules.tier.null → правила доступа
    POST  /api/posts/new   {post_type: text_only, post_visibility: paid} → черновик
    POST  /api/media       {owner: post, audio, pending_upload}          → S3 presigned
    POST  <upload_url>     multipart: upload_parameters + file
    GET   /api/media/{id}                                    → ждём state=ready
    PATCH /api/posts/{id}  post_type podcast, content_json_string, access_rules,
                           tags.publish=true, meta.auto_save=false
    GET   /api/posts/{id}                                    → проверка published_at
"""

from __future__ import annotations

import asyncio
import json
from html import escape
from pathlib import Path

import httpx
from loguru import logger
from sagenza_tgbot_sdk.masking import register_secrets
from sagenza_tgbot_sdk.resilience import PermanentError

BASE_URL = "https://www.patreon.com"
_JSONAPI = {"json-api-version": "1.0"}
_NO_DEFAULTS = {"json-api-use-default-includes": "false"}
_TIMEOUT = httpx.Timeout(60.0, read=600.0, write=600.0)
_MEDIA_POLL_ATTEMPTS = 30


class PatreonAuthError(PermanentError):
    HINT = (
        "Обновите secrets/patreon/patreon_session.json: войдите на patreon.com и "
        "выполните `python smoke.py import-cookie` (см. app/publishers/Patreon/SMOKE.md)."
    )

    def __init__(self, reason: str) -> None:
        super().__init__(f"Patreon: {reason}. {self.HINT}")


class PatreonApiError(RuntimeError):
    def __init__(self, what: str, response: httpx.Response) -> None:
        super().__init__(f"Patreon {what} → HTTP {response.status_code}: {response.text[:500]}")
        self.status = response.status_code


def load_session(path: str) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise PatreonAuthError(f"нет файла сессии {path}") from e
    except ValueError as e:
        raise PatreonAuthError(f"файл сессии {path} повреждён") from e
    if not isinstance(raw, dict) or not raw.get("session_id"):
        raise PatreonAuthError(f"в {path} нет session_id")
    # Кука сессии не должна попасть в логи и в текст ошибки, который уходит боту.
    register_secrets(str(raw["session_id"]))
    return raw


def save_session(path: str, session_id: str, user_agent: str | None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"session_id": session_id.strip(), "user_agent": user_agent}), encoding="utf-8")


def pick_access_rules(included: list[dict], tier_ids: list[str]) -> list[str]:
    """id правил доступа: по заданным уровням или «все платные патроны»."""
    rules = [item for item in included if item.get("type") == "access-rule"]
    if tier_ids:
        wanted = set(tier_ids)
        picked = [
            rule["id"]
            for rule in rules
            if (((rule.get("relationships") or {}).get("tier") or {}).get("data") or {}).get("id") in wanted
        ]
    else:
        picked = [rule["id"] for rule in rules if (rule.get("attributes") or {}).get("access_rule_type") == "patrons"]
    if not picked:
        raise PermanentError(
            f"Patreon: не нашлось правил доступа для уровней {tier_ids or 'patrons'}, проверьте PATREON_TIER_IDS"
        )
    return picked


def editor_document(lines: list[str]) -> str:
    """Тело поста в формате редактора (content_json_string): замок и абзацы.

    ``paywallBreakpoint`` в начале документа закрывает весь текст под ним
    для тех, у кого нет доступа; так его ставит редактор для платного поста.
    """
    content: list[dict] = [
        {
            "type": "paywallBreakpoint",
            "attrs": {"paywallBreakpointCtaProps": {"isPaidAccessSelected": True, "isPaidMembersSelected": True}},
        }
    ]
    content += [{"type": "paragraph", "content": [{"type": "text", "text": line}]} for line in lines]
    return json.dumps({"type": "doc", "content": content}, ensure_ascii=False)


class PatreonClient:
    def __init__(
        self,
        session_file: str,
        tier_ids: list[str],
        http: httpx.AsyncClient | None = None,
        media_poll_delay: float = 2.0,
    ) -> None:
        self.session_file = session_file
        self.tier_ids = tier_ids
        self._http = http
        self._csrf: str | None = None
        self.campaign_id: str | None = None
        self.media_poll_delay = media_poll_delay

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            session = await asyncio.to_thread(load_session, self.session_file)
            headers = {"User-Agent": session.get("user_agent") or "Mozilla/5.0", "Origin": BASE_URL}
            self._http = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=_TIMEOUT,
                headers=headers,
                cookies={"session_id": session["session_id"]},
                follow_redirects=True,
            )
        return self._http

    async def _request(self, what: str, method: str, url: str, *, params: dict | None = None, **kwargs) -> dict:
        http = await self._client()
        headers = {"Content-Type": "application/vnd.api+json"} if "json" in kwargs else {}
        if method != "GET":
            headers["X-CSRF-Signature"] = await self._csrf_signature()
        body = kwargs.pop("json", None)
        content = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        resp = await http.request(
            method, url, params={**_JSONAPI, **(params or {})}, headers=headers, content=content, **kwargs
        )
        if resp.status_code in (401, 403):
            raise PatreonAuthError(f"{what}: HTTP {resp.status_code}, сессия не принята")
        if resp.status_code >= 400:
            raise PatreonApiError(what, resp)
        return resp.json() if resp.content else {}

    async def _csrf_signature(self) -> str:
        """Подпись для X-CSRF-Signature: редактор берёт её у CSRFTicket."""
        if self._csrf is None:
            http = await self._client()
            resp = await http.get("/REST/auth/CSRFTicket", params={"uri": "/", **_JSONAPI})
            token = resp.json().get("token") if resp.status_code == 200 and resp.content else None
            if not token:
                raise PatreonAuthError(f"CSRFTicket: HTTP {resp.status_code}, подпись не выдана")
            register_secrets(str(token))
            self._csrf = str(token)
        return self._csrf

    async def ensure_auth(self) -> str:
        """Проверяет сессию и находит кампанию. Возвращает id кампании."""
        if self.campaign_id:
            return self.campaign_id
        body = await self._request("current_user", "GET", "/api/current_user", params={"include": "campaign"})
        campaign = ((body.get("data") or {}).get("relationships") or {}).get("campaign") or {}
        campaign_id = (campaign.get("data") or {}).get("id")
        if not campaign_id:
            raise PatreonAuthError("у аккаунта нет кампании автора")
        self.campaign_id = str(campaign_id)
        return self.campaign_id

    async def access_rules(self) -> list[str]:
        campaign_id = await self.ensure_auth()
        body = await self._request(
            "campaign",
            "GET",
            f"/api/campaigns/{campaign_id}",
            params={
                "include": "access_rules.tier.null",
                "fields[access-rule]": "access_rule_type,amount_cents,currency",
            },
        )
        return pick_access_rules(body.get("included") or [], self.tier_ids)

    async def create_draft(self) -> str:
        body = await self._request(
            "create draft",
            "POST",
            "/api/posts/new",
            params={"fields[post]": "edit_url", **_NO_DEFAULTS, "json-api-use-default-fields": "false"},
            json={"data": {"type": "post", "attributes": {"post_type": "text_only", "post_visibility": "paid"}}},
        )
        return str(body["data"]["id"])

    async def upload_audio(self, post_id: str, path: str) -> str:
        """Регистрирует медиа у поста, грузит файл на presigned S3 и ждёт обработки."""
        file = Path(path)
        size = file.stat().st_size
        body = await self._request(
            "create media",
            "POST",
            "/api/media",
            params={**_NO_DEFAULTS, "include": "[]"},
            json={
                "data": {
                    "type": "media",
                    "attributes": {
                        "state": "pending_upload",
                        "file_name": file.name,
                        "size_bytes": size,
                        "owner_id": post_id,
                        "owner_type": "post",
                        "owner_relationship": "audio",
                        "media_type": "audio",
                    },
                }
            },
        )
        media_id = str(body["data"]["id"])
        attrs = body["data"]["attributes"]
        content = await asyncio.to_thread(file.read_bytes)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as s3:
            resp = await s3.post(
                attrs["upload_url"],
                data=attrs.get("upload_parameters") or {},
                files={"file": (file.name, content, "audio/mpeg")},
                headers={"Origin": BASE_URL},
            )
        if resp.status_code >= 400:
            raise PatreonApiError("s3 upload", resp)
        await self._wait_media_ready(media_id)
        return media_id

    async def _wait_media_ready(self, media_id: str) -> None:
        state = None
        for _ in range(_MEDIA_POLL_ATTEMPTS):
            body = await self._request("get media", "GET", f"/api/media/{media_id}", params={"fields[media]": "state"})
            state = ((body.get("data") or {}).get("attributes") or {}).get("state")
            if state == "ready":
                return
            if state in ("failed", "error"):
                raise PermanentError(f"Patreon: файл не обработан (state={state})")
            await asyncio.sleep(self.media_poll_delay)
        raise RuntimeError(f"Patreon media {media_id} не готов (state={state})")

    async def publish(self, post_id: str, *, title: str, lines: list[str], rule_ids: list[str]) -> str | None:
        """Публикует черновик аудиопостом под замком. Возвращает ссылку на пост."""
        rules = [{"type": "access-rule", "id": rule_id} for rule_id in rule_ids]
        body = await self._request(
            "publish",
            "PATCH",
            f"/api/posts/{post_id}",
            params=_NO_DEFAULTS,
            json={
                "data": {
                    "type": "post",
                    "attributes": {
                        "title": title,
                        "content": "".join(f"<p>{escape(line)}</p>" for line in lines),
                        "content_json_string": editor_document(lines),
                        "post_type": "podcast",
                        "is_paid": False,
                        "is_monetized": False,
                        "paywall_display": "post_layout",
                        "new_post_email_type": "preview_only",
                        "comments_write_access_level": "all",
                        "preview_asset_type": "default",
                        "post_metadata": {"platform": {}},
                        "tags": {"publish": True},
                    },
                    "relationships": {
                        "access-rule": {"data": rules[0]},
                        "access_rules": {"data": rules},
                        "user_defined_tags": {"data": []},
                    },
                },
                "meta": {"auto_save": False, "send_notifications": True},
                "included": [{**rule, "attributes": {}} for rule in rules],
            },
        )
        logger.success(f"Patreon post published (id={post_id})")
        return ((body.get("data") or {}).get("attributes") or {}).get("url")

    async def get_post(self, post_id: str) -> dict | None:
        body = await self._request("get post", "GET", f"/api/posts/{post_id}")
        data = body.get("data")
        if not data or not (data.get("attributes") or {}).get("published_at"):
            return None
        return data

    @staticmethod
    def post_url(post_id: str) -> str:
        return f"{BASE_URL}/posts/{post_id}"

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
