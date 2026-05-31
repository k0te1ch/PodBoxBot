"""Тонкая обёртка над `barsikus007/boosty` для постинга с tier-привязкой.

Почему не «голый» `API.create_post`: его модель `NewPost` НЕ сериализует
`subscription_level_id`, а именно это поле привязывает пост к уровню
подписки (см. спайк `.planning/spikes/boosty-sponsr-feasibility.md`,
секция Paywall/tiers). Поэтому create-post шлём **сырым form-payload**
через переиспользуемый `API.request(...)` — он сам подставляет
`Authorization`-заголовок и обновляет токен по 401 (refresh_token +
device_id из auth.json).

Auth-bootstrap: один раз вручную логинимся в браузере, экспортируем
`auth.json` (access_token / refresh_token / device_id / expires_at /
user_agent) в `BOOSTY_AUTH_FILE`. `FileAuthDataResolver` читает/перезаписывает
этот файл; refresh — внутри либы.

Известный риск: `API.request` шлёт только базовые заголовки (UA +
Authorization), без `X-App/X-Currency/X-Locale`. Собственный create_post
либы работает так же, поэтому считаем достаточным; если internal-API
начнёт требовать X-*, добавляем свой aiohttp-вызов (см. спайк, п. 4б).
"""

from __future__ import annotations

import asyncio

from content import build_post_data
from loguru import logger

# Импорт либы изолирован: при отсутствии пакета (например, в unit-окружении
# без установленного boosty) модуль всё равно импортируется, а понятная
# ошибка всплывёт только при реальном построении клиента.
try:
    from boosty.api import API
    from boosty.api.auth import Auth
    from boosty.api.auth.resolvers.file import FileAuthDataResolver

    _IMPORT_ERROR: Exception | None = None
except Exception as e:  # pragma: no cover - зависит от окружения
    API = Auth = FileAuthDataResolver = None  # type: ignore[assignment]
    _IMPORT_ERROR = e


class BoostyClient:
    """Stateful-обёртка: один блог, ленивое построение API + кэш уровней."""

    def __init__(self, blog_name: str, auth_file: str) -> None:
        # Пустой blog_name допустим при конструировании (импорт модуля при
        # незаданном BOOSTY_BLOG не должен падать); проверяем в ensure_auth.
        self.blog_name = blog_name
        self.auth_file = auth_file
        self._api: API | None = None  # type: ignore[valid-type]
        self._levels: dict[str, str] | None = None  # name(lower) -> id

    # --- auth ---

    async def ensure_auth(self) -> None:
        """Строит API из auth.json (blocking IO → to_thread) и валидирует токен.

        Идемпотентно: повторные вызовы — no-op. Сам refresh по 401 делает
        `API.request`; здесь только начальная загрузка + понятная ошибка,
        если файл с токеном не подготовлен.
        """
        if self._api is not None:
            return
        if not self.blog_name:
            raise RuntimeError("BOOSTY_BLOG is not configured")
        if _IMPORT_ERROR is not None:
            raise RuntimeError(f"boosty library is not available: {_IMPORT_ERROR!r}")

        def _build() -> API:  # type: ignore[valid-type]
            auth = Auth(FileAuthDataResolver(self.auth_file))
            return API(auth=auth)

        api = await asyncio.to_thread(_build)
        if not getattr(api.auth.auth_data, "access_token", None):
            raise RuntimeError(
                f"No access_token in {self.auth_file}. Export auth.json from a "
                "browser session (access_token/refresh_token/device_id)."
            )
        self._api = api
        logger.debug(f"Boosty auth loaded for blog '{self.blog_name}'")

    # --- subscription levels ---

    async def resolve_level_id(self, tier: str) -> str:
        """Преобразует tier (имя уровня или сырой id) в `subscription_level_id`.

        Числовая строка трактуется как готовый id. Иначе ищем уровень по
        имени (case-insensitive) среди уровней блога.
        """
        tier = (tier or "").strip()
        if not tier:
            raise ValueError("Empty tier — cannot resolve subscription_level_id")
        if tier.isdigit():
            return tier

        levels = await self._get_levels()
        level_id = levels.get(tier.lower())
        if level_id is None:
            raise ValueError(
                f"Subscription level '{tier}' not found for blog '{self.blog_name}'. Available: {sorted(levels)}"
            )
        return level_id

    async def _get_levels(self) -> dict[str, str]:
        if self._levels is not None:
            return self._levels
        await self.ensure_auth()
        assert self._api is not None
        resp = await self._api.request(
            "GET",
            f"/v1/blog/{self.blog_name}/subscription_level/",
            params={"show_deleted": "false", "show_free_level": "true"},
        )
        items = resp.get("data", resp) if isinstance(resp, dict) else resp
        levels: dict[str, str] = {}
        for item in items or []:
            name = item.get("name")
            level_id = item.get("id")
            if name is not None and level_id is not None:
                levels[str(name).strip().lower()] = str(level_id)
        self._levels = levels
        logger.debug(f"Resolved Boosty levels: {levels}")
        return levels

    # --- posting ---

    async def create_post(
        self,
        *,
        title: str,
        body: str,
        subscription_level_id: str,
        chapters: list[list[str]] | None = None,
        tags: str = "",
        price: str = "0",
    ) -> str:
        """Создаёт пост сырым form-payload. Возвращает id созданного поста."""
        await self.ensure_auth()
        assert self._api is not None

        payload = {
            "title": title,
            "data": build_post_data(body, chapters),
            "subscription_level_id": str(subscription_level_id),
            "price": price,
            "teaser_data": "[]",
            "tags": tags,
            "deny_comments": "false",
            "wait_video": "false",
            "has_chat": "false",
            "advertiser_info": "",  # обязательное поле; пустое допустимо
        }
        resp = await self._api.request("POST", f"/v1/blog/{self.blog_name}/post/", data=payload)
        post_id = ""
        if isinstance(resp, dict):
            post_id = str(resp.get("id") or resp.get("data", {}).get("id", ""))
        logger.success(f"Boosty post created (id={post_id or '?'})")
        return post_id
