"""Вход в Boosty из браузерных кук: разбор того, что прислал админ, и файл токенов.

Программного логина у Boosty нет, сессию даёт только браузер: кука ``auth``
(URL-encoded JSON с accessToken, refreshToken, expiresAt) и кука ``_clientId``
(device_id для обновления токена). Обе читаются из JavaScript страницы, поэтому
админ копирует их одной строкой сниппетом из консоли браузера (:data:`SNIPPET`).

Принимаются три формы:

* строка сниппета: ``PODBOX-BOOSTY {"auth": ..., "clientId": ..., "ua": ...}``;
* заголовок ``Cookie`` из вкладки Network: ``...; auth=...; _clientId=...``;
* JSON-выгрузка кук расширением: ``[{"name": "auth", "value": ...}, ...]``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import unquote

MARKER = "PODBOX-BOOSTY"

SNIPPET = (
    "copy('" + MARKER + " '+JSON.stringify({"
    "auth:document.cookie.match(/(?:^|; )auth=([^;]*)/)[1],"
    "clientId:document.cookie.match(/(?:^|; )_clientId=([^;]*)/)[1],"
    "ua:navigator.userAgent}))"
)


class CookieError(ValueError):
    """Присланный текст не годится как вход в Boosty; текст объясняет почему."""


@dataclass
class BrowserLogin:
    auth_cookie: str
    client_id: str
    user_agent: str | None = None


def looks_like_cookies(text: str | None) -> bool:
    """Похоже ли сообщение на присланные куки Boosty, а не на обычный текст."""
    if not text:
        return False
    return MARKER in text or ("auth=" in text and "_clientId=" in text) or ('"_clientId"' in text and '"auth"' in text)


def parse(text: str) -> BrowserLogin:
    text = text.strip()
    if MARKER in text:
        return _from_snippet(text.split(MARKER, 1)[1])
    if text.startswith("["):
        return _from_export(text)
    return _from_header(text)


def _from_snippet(payload: str) -> BrowserLogin:
    try:
        raw = json.loads(payload.strip())
    except ValueError as e:
        raise CookieError("строка из сниппета обрезана, скопируй её целиком") from e
    return _login(raw.get("auth"), raw.get("clientId"), raw.get("ua"))


def _from_export(payload: str) -> BrowserLogin:
    try:
        cookies = {item["name"]: item["value"] for item in json.loads(payload) if isinstance(item, dict)}
    except (ValueError, KeyError, TypeError) as e:
        raise CookieError("это не выгрузка кук: ждал список с name и value") from e
    return _login(cookies.get("auth"), cookies.get("_clientId"), None)


def _from_header(payload: str) -> BrowserLogin:
    payload = re.sub(r"^\s*cookie\s*:\s*", "", payload, flags=re.IGNORECASE)
    cookies = {}
    for part in payload.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep:
            cookies[name.strip()] = value.strip()
    return _login(cookies.get("auth"), cookies.get("_clientId"), None)


def _login(auth_cookie, client_id, user_agent) -> BrowserLogin:
    if not auth_cookie:
        raise CookieError("нет куки auth: войди на boosty.to и скопируй заново")
    if not client_id:
        raise CookieError("нет куки _clientId")
    return BrowserLogin(str(auth_cookie), str(client_id).strip(), user_agent or None)


def auth_file_data(login: BrowserLogin) -> dict:
    """Содержимое ``boosty_auth.json`` в формате, который читает публишер."""
    try:
        raw = json.loads(unquote(login.auth_cookie.strip()))
    except ValueError as e:
        raise CookieError("кука auth должна быть URL-encoded JSON с accessToken и refreshToken") from e
    if not isinstance(raw, dict) or not raw.get("accessToken") or not raw.get("refreshToken"):
        raise CookieError("в куке auth нет accessToken и refreshToken: ты вошёл в аккаунт?")
    # Истёкший accessToken не беда: публишер обменяет refreshToken на новую пару.
    return {
        "access_token": raw["accessToken"],
        "refresh_token": raw["refreshToken"],
        "expires_at": to_epoch_seconds(raw.get("expiresAt")),
        "device_id": login.client_id,
        "user_agent": login.user_agent,
    }


def to_epoch_seconds(value) -> int | None:
    """expires_at бывает в секундах (ответ refresh) и в мс (кука браузера)."""
    if value in (None, ""):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number // 1000 if number > 10**11 else number
