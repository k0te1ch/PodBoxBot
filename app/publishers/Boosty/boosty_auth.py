"""Токены Boosty: файл auth.json, импорт из браузерных кук, срок жизни.

Программного логина у Boosty нет: токены выдаёт только браузерная сессия.
Владелец один раз логинится на boosty.to, копирует куки ``auth`` и
``_clientId`` и превращает их в auth.json командой ``smoke.py import-cookie``.
Дальше сервис живёт на refresh_token: ``POST /oauth/token/`` с
``grant_type=refresh_token`` и ``device_id`` (так делает веб-клиент Boosty).

Формат файла совпадает с тем, что писала прежняя либа ``boosty``
(access_token / refresh_token / expires_at / device_id / user_agent), поэтому
старый ``secrets/boosty/boosty_auth.json`` читается без миграции.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote

from sagenza_tgbot_sdk.resilience import PermanentError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
# Обновлять токен заранее: публикация длинного mp3 занимает минуты, и токен,
# живой на старте, может истечь посреди загрузки чанков.
REFRESH_MARGIN = 600  # сек


class BoostyAuthError(PermanentError):
    """Авторизация Boosty не работает, и повтор запроса её не починит.

    Текст уходит в failure-событие и показывается админу в боте, поэтому он
    объясняет, что сделать, а не только что сломалось.
    """

    HINT = (
        "Обновите secrets/boosty/boosty_auth.json: войдите на boosty.to в браузере и "
        "выполните `python smoke.py import-cookie` (см. app/publishers/Boosty/SMOKE.md)."
    )

    def __init__(self, reason: str) -> None:
        super().__init__(f"Boosty: {reason}. {self.HINT}")
        self.reason = reason


@dataclass
class AuthData:
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: int | None = None
    device_id: str | None = None
    user_agent: str | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> AuthData:
        return cls(
            access_token=raw.get("access_token") or None,
            refresh_token=raw.get("refresh_token") or None,
            expires_at=_to_epoch_seconds(raw.get("expires_at")),
            device_id=raw.get("device_id") or None,
            user_agent=raw.get("user_agent") or None,
        )

    @classmethod
    def from_cookies(cls, auth_cookie: str, client_id: str, user_agent: str | None = None) -> AuthData:
        """Из значения куки ``auth`` (URL-encoded JSON) и куки ``_clientId``."""
        try:
            raw = json.loads(unquote(auth_cookie.strip()))
        except ValueError as e:
            raise ValueError("Кука auth должна быть URL-encoded JSON с accessToken/refreshToken") from e
        if not raw.get("accessToken") or not raw.get("refreshToken"):
            raise ValueError("В куке auth нет accessToken/refreshToken — вы вошли в аккаунт?")
        if not client_id.strip():
            raise ValueError("Нужна кука _clientId: это device_id для refresh")
        return cls(
            access_token=raw["accessToken"],
            refresh_token=raw["refreshToken"],
            expires_at=_to_epoch_seconds(raw.get("expiresAt")),
            device_id=client_id.strip(),
            user_agent=user_agent,
        )

    def apply_refresh(self, response: dict) -> None:
        """Обновляет токены из ответа ``/oauth/token/``."""
        try:
            self.access_token = response["access_token"]
            self.refresh_token = response.get("refresh_token") or self.refresh_token
            self.expires_at = int(time.time()) + int(response["expires_in"])
        except (KeyError, TypeError, ValueError) as e:
            raise BoostyAuthError(f"неожиданный ответ refresh: {response!r}") from e

    def expires_soon(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now if now is not None else time.time()) + REFRESH_MARGIN >= self.expires_at

    def to_dict(self) -> dict:
        return asdict(self)


def _to_epoch_seconds(value) -> int | None:
    """expires_at бывает в секундах (ответ refresh) и в мс (кука браузера)."""
    if value in (None, ""):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number // 1000 if number > 10**11 else number


def load(path: str | Path) -> AuthData:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise BoostyAuthError(f"нет файла токенов {path}") from e
    except ValueError as e:
        raise BoostyAuthError(f"файл токенов {path} повреждён") from e
    data = AuthData.from_dict(raw if isinstance(raw, dict) else {})
    if not data.access_token or not data.refresh_token or not data.device_id:
        raise BoostyAuthError(f"в {path} не хватает access_token, refresh_token или device_id")
    return data


def save(path: str | Path, data: AuthData) -> None:
    """Атомарная запись: упавший посреди записи процесс не оставит битый файл."""
    target = Path(path)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
