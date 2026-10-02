"""VK ID OAuth 2.1 (PKCE): долгоживущий доступ к публикации без ручного входа раз в час.

Зачем это нужно
---------------
Ключ пользователя VK живёт 1 час. Раньше держать доступ помогало право
``offline`` (бессрочный ключ), но в VK ID его больше нет. Вместо него VK ID
выдаёт пару ``access_token`` (1 час) + ``refresh_token`` (180 дней). Пока сервис
обновляет пару хотя бы раз в 180 дней, цепочка живёт практически бессрочно и
ручной вход нужен ровно один раз.

Как это работает
----------------
* Один раз владелец сообщества открывает ссылку авторизации (``authorize_url``),
  нажимает «Разрешить» и передаёт одноразовый ``code`` + ``device_id``. Обмен
  (``exchange_code``) даёт первую пару токенов, она пишется в ``VK_AUTH_FILE``.
* Дальше ``access_token()`` сам обновляет пару заранее (за ``REFRESH_MARGIN`` до
  истечения) и по ошибке авторизации. Ротация у VK ID одноразовая: каждый refresh
  возвращает **новую** пару, старый refresh сразу умирает, поэтому пишем атомарно
  и под межпроцессной блокировкой.
* ``refresh_token`` живёт 180 дней. Если публикаций долго нет, фоновая задача в
  main.py всё равно обновляет пару и продлевает этот срок; а если до конца срока
  осталось мало, админам уходит предупреждение заранее.

Пароль владельца в код не попадает: вход — только через браузер владельца.

Ссылки VK ID: обмен и обновление — ``POST https://id.vk.ru/oauth2/auth``;
ссылка согласия — ``https://id.vk.ru/authorize`` (PKCE, ``code_challenge_method=S256``).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx
from loguru import logger
from sagenza_tgbot_sdk.resilience import PermanentError

AUTH_URL = "https://id.vk.ru/oauth2/auth"
AUTHORIZE_URL = "https://id.vk.ru/authorize"

# access_token живёт 3600 с; обновляем заранее, чтобы публикация длинного mp3 не
# началась с уже протухшим ключом.
REFRESH_MARGIN = 600  # сек
# refresh_token живёт 180 дней; отсчитываем срок от последнего обновления.
REFRESH_TOKEN_TTL = 180 * 24 * 3600  # сек


class VkAuthError(PermanentError):
    """Авторизация VK ID не работает, и повтор запроса её не починит.

    Текст уходит в failure-событие и показывается админам, поэтому объясняет,
    что сделать, а не только что сломалось.
    """

    HINT = (
        "Обновите доступ VK: откройте ссылку авторизации из предупреждения бота, "
        "нажмите «Разрешить» и передайте код (см. app/publishers/VK/SMOKE.md)."
    )

    def __init__(self, reason: str) -> None:
        super().__init__(f"VK ID: {reason}. {self.HINT}")
        self.reason = reason


@dataclass
class VkAuthData:
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: int | None = None  # когда протухает access_token (epoch, сек)
    refresh_expires_at: int | None = None  # когда протухает refresh_token (epoch, сек)
    device_id: str | None = None
    user_id: int | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> VkAuthData:
        return cls(
            access_token=raw.get("access_token") or None,
            refresh_token=raw.get("refresh_token") or None,
            expires_at=_as_int(raw.get("expires_at")),
            refresh_expires_at=_as_int(raw.get("refresh_expires_at")),
            device_id=raw.get("device_id") or None,
            user_id=_as_int(raw.get("user_id")),
        )

    def apply_token_response(self, response: dict, now: float | None = None) -> None:
        """Обновляет токены из ответа ``/oauth2/auth`` (обмен или refresh)."""
        now = time.time() if now is None else now
        try:
            self.access_token = response["access_token"]
            self.refresh_token = response.get("refresh_token") or self.refresh_token
            self.expires_at = int(now) + int(response["expires_in"])
        except (KeyError, TypeError, ValueError) as e:
            raise VkAuthError(f"неожиданный ответ токена: {_safe(response)}") from e
        if response.get("refresh_token"):
            # Каждый успешный refresh продлевает срок refresh_token ещё на 180 дней.
            self.refresh_expires_at = int(now) + REFRESH_TOKEN_TTL
        if response.get("user_id"):
            self.user_id = _as_int(response.get("user_id"))

    def access_expires_soon(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return True
        return (time.time() if now is None else now) + REFRESH_MARGIN >= self.expires_at

    def refresh_seconds_left(self, now: float | None = None) -> int | None:
        if self.refresh_expires_at is None:
            return None
        return int(self.refresh_expires_at - (time.time() if now is None else now))

    def to_dict(self) -> dict:
        return asdict(self)


def _as_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe(response: dict) -> str:
    """Ответ для лога без секретов: коды ошибок VK ID видны, токены — нет."""
    if not isinstance(response, dict):
        return type(response).__name__
    shown = {k: v for k, v in response.items() if k in {"error", "error_description", "error_code", "state"}}
    return str(shown or {"keys": sorted(response)})


def load(path: str | Path) -> VkAuthData:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise VkAuthError(f"нет файла токенов {path}") from e
    except ValueError as e:
        raise VkAuthError(f"файл токенов {path} повреждён") from e
    data = VkAuthData.from_dict(raw if isinstance(raw, dict) else {})
    if not data.refresh_token or not data.device_id:
        raise VkAuthError(f"в {path} не хватает refresh_token или device_id — нужен вход заново")
    return data


def save(path: str | Path, data: VkAuthData) -> None:
    """Атомарная запись: упавший посреди записи процесс не оставит битый файл."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def make_pkce() -> tuple[str, str]:
    """Пара (code_verifier, code_challenge) для PKCE S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def authorize_url(client_id: int, redirect_uri: str, code_challenge: str, state: str, scope: str) -> str:
    """Ссылка согласия VK ID: владелец открывает её и нажимает «Разрешить»."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": scope,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


class VkAuth:
    """Держит пару токенов VK ID в файле и обновляет её по мере надобности."""

    def __init__(
        self,
        client_id: int | None,
        auth_file: str,
        *,
        client_secret: str | None = None,
        redirect_uri: str = "",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id
        self.auth_file = auth_file
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.http = http or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._lock = asyncio.Lock()
        self._data: VkAuthData | None = None

    def _require_client_id(self) -> int:
        if not self.client_id:
            raise VkAuthError("не задан VK_CLIENT_ID приложения VK ID")
        return self.client_id

    async def _load(self) -> VkAuthData:
        if self._data is None:
            self._data = await asyncio.to_thread(load, self.auth_file)
        return self._data

    async def _save(self, data: VkAuthData) -> None:
        self._data = data
        await asyncio.to_thread(save, self.auth_file, data)

    async def _post_token(self, params: dict) -> dict:
        data = {k: v for k, v in params.items() if v is not None}
        data["client_id"] = self._require_client_id()
        if self.client_secret:
            data["client_secret"] = self.client_secret
        try:
            resp = await self.http.post(AUTH_URL, data=data)
        except httpx.HTTPError as e:
            # Сеть/сервис — временная беда, но наверх отдаём как есть: main
            # решит, ретраить или предупреждать.
            raise VkAuthError(f"сеть VK ID недоступна: {type(e).__name__}") from e
        body = resp.json() if resp.content else {}
        if resp.status_code >= 400 or body.get("error"):
            raise VkAuthError(f"отказ VK ID [{resp.status_code}]: {_safe(body)}")
        return body

    async def exchange_code(self, code: str, device_id: str, code_verifier: str, state: str = "") -> VkAuthData:
        """Первый обмен: одноразовый ``code`` из браузера → пара токенов."""
        body = await self._post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "device_id": device_id,
                "redirect_uri": self.redirect_uri or None,
                "state": state or None,
            }
        )
        data = VkAuthData(device_id=device_id)
        data.apply_token_response(body)
        await self._save(data)
        logger.success("VK ID: получена первая пара токенов")
        return data

    async def refresh(self, *, force: bool = False) -> VkAuthData:
        """Обновляет пару токенов. По умолчанию — только если access скоро истечёт."""
        async with self._lock:
            data = await self._load()
            if not force and not data.access_expires_soon():
                return data
            body = await self._post_token(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": data.refresh_token,
                    "device_id": data.device_id,
                    "state": secrets.token_urlsafe(8),
                }
            )
            data.apply_token_response(body)
            await self._save(data)
            logger.info("VK ID: пара токенов обновлена")
            return data

    async def access_token(self) -> str:
        """Валидный access_token: при необходимости обновляет пару."""
        data = await self._load()
        if data.access_expires_soon():
            data = await self.refresh(force=True)
        if not data.access_token:
            raise VkAuthError("нет access_token после обновления")
        return data.access_token

    async def status(self) -> VkAuthData:
        """Текущее состояние токенов для проверки/предупреждений (без обновления)."""
        return await self._load()
