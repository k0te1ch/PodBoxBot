"""Метрики PodBoxBot сверх того, что считает SDK.

Модуль metrics из sagenza-tgbot-sdk считает апдейты, ошибки и время
хендлеров и отдаёт свой реестр на ``/metrics`` (порт health-сервера). Здесь в
тот же реестр добавляется то, что знает только бот:

* бизнес-события через ``Metrics.event``: они видны как
  ``sagenza_event_<имя>_total{bot="podboxbot", ...}``;
* гистограммы и gauge ``podboxbot_*``: время от загрузки mp3 до публикации,
  размер и длительность аудио, состояние RSS, активность админов, версия;
* метрики процесса Python (``process_*``, ``python_*``): у реестра SDK их нет.

Метки только с коротким известным набором значений: площадка, тип эпизода,
шаг, действие, класс ошибки. Никаких id пользователей, имён файлов и текстов.

Сбой метрик не должен мешать боту: каждый публичный метод ловит свои
исключения и пишет warning.
"""

from __future__ import annotations

import functools
import inspect
import re
import time
from collections.abc import Callable, Iterator
from typing import Any, ParamSpec

from loguru import logger
from prometheus_client import GC_COLLECTOR, PLATFORM_COLLECTOR, PROCESS_COLLECTOR, Gauge, Histogram
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from redis.asyncio import Redis
from sagenza_tgbot_sdk.metrics import Metrics

import config as bot_config

BOT_NAME = "podboxbot"

# Площадки, как их называет бот в метках. ``telegram`` это пересылка в чат.
FTP = "ftp"
SITE = "wp"
TELEGRAM = "telegram"
BOOSTY = "boosty"
PAYWALLED = ("vk", "patreon", "sponsr")

# Имя файла эпизода (generate_file_name): 0767_rz_26092026.mp3, 0123_postshow_….mp3.
_FILE_NUMBER = re.compile(r"^(\d+)_")

# Эпизод помнится месяц: дольше публикацию одного выпуска не растягивают.
LEDGER_TTL = 30 * 24 * 3600
LEDGER_KEY = "metrics:episode:{type_episode}:{number}"

ACTIVITY_WINDOWS = {"1d": 24 * 3600, "7d": 7 * 24 * 3600}

MINUTE = 60
HOUR = 3600
DAY = 24 * HOUR
PUBLISH_BUCKETS = (
    MINUTE,
    5 * MINUTE,
    15 * MINUTE,
    30 * MINUTE,
    HOUR,
    2 * HOUR,
    6 * HOUR,
    12 * HOUR,
    DAY,
    3 * DAY,
    7 * DAY,
)
MB = 1024 * 1024
SIZE_BUCKETS = (10 * MB, 25 * MB, 50 * MB, 100 * MB, 200 * MB, 400 * MB, 800 * MB, 2000 * MB)
DURATION_BUCKETS = (10 * MINUTE, 30 * MINUTE, HOUR, 90 * MINUTE, 2 * HOUR, 3 * HOUR, 4 * HOUR, 6 * HOUR)
DOWNLOAD_BUCKETS = (5, 15, 30, MINUTE, 2 * MINUTE, 5 * MINUTE, 10 * MINUTE, 30 * MINUTE)

P = ParamSpec("P")


def _never_fails(func: Callable[P, Any]) -> Callable[P, Any]:
    """Метрика упала: пишем warning, бот продолжает работу."""
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"metrics: {func.__name__} failed: {e!r}")
                return None

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"metrics: {func.__name__} failed: {e!r}")
            return None

    return wrapper


def episode_kind(type_episode: str | None) -> str:
    """``main`` или ``aftershow``; ``postshow`` это старое имя послешоу."""
    if type_episode == "main":
        return "main"
    if type_episode in ("aftershow", "postshow"):
        return "aftershow"
    return "unknown"


def episode_number(number: Any = None, file_name: str | None = None) -> str | None:
    """Номер эпизода без ведущих нулей: из поля события или из имени mp3."""
    raw = str(number) if number not in (None, "") else None
    if raw is None and file_name:
        match = _FILE_NUMBER.match(file_name.rsplit("/", 1)[-1])
        raw = match.group(1) if match else None
    if raw is None or not raw.isdigit():
        return None
    return str(int(raw))


class EpisodeLedger:
    """Когда эпизод загружен и где уже опубликован; хеш в Redis на эпизод.

    Нужен для времени от загрузки до публикации и для счёта повторных
    нажатий. Без Redis всё это просто не считается.
    """

    def __init__(self, redis: Redis | None) -> None:
        self.redis = redis

    @staticmethod
    def _key(number: str, kind: str) -> str:
        return LEDGER_KEY.format(type_episode=kind, number=number)

    async def uploaded(self, number: str, kind: str, at: float) -> None:
        if self.redis is None:
            return
        key = self._key(number, kind)
        await self.redis.hset(key, mapping={"uploaded_at": at})
        await self.redis.expire(key, LEDGER_TTL)

    async def count_request(self, number: str, kind: str, platform: str) -> int:
        """Сколько раз уже просили опубликовать эпизод на площадке, включая этот."""
        if self.redis is None:
            return 1
        key = self._key(number, kind)
        count = int(await self.redis.hincrby(key, f"requests:{platform}", 1))
        await self.redis.expire(key, LEDGER_TTL)
        return count

    async def published(self, number: str, kind: str, platform: str, at: float) -> tuple[bool, float | None]:
        """Отмечает публикацию; (первая ли на площадке, время загрузки эпизода)."""
        if self.redis is None:
            return True, None
        key = self._key(number, kind)
        first = bool(await self.redis.hsetnx(key, f"published:{platform}", at))
        await self.redis.expire(key, LEDGER_TTL)
        uploaded_at = await self.redis.hget(key, "uploaded_at")
        return first, float(uploaded_at) if uploaded_at else None

    async def published_everywhere(self, number: str, kind: str, platforms: set[str]) -> bool:
        """True один раз: когда эпизод впервые есть на всех ``platforms``."""
        if self.redis is None or not platforms:
            return False
        key = self._key(number, kind)
        fields = await self.redis.hmget(key, [f"published:{p}" for p in sorted(platforms)])
        if not all(fields):
            return False
        return bool(await self.redis.hsetnx(key, "published:all", time.time()))


class _AdminActivity(Collector):
    """Сколько разных админов что-то делали за окно; id наружу не выходят."""

    def __init__(self) -> None:
        self._last_seen: dict[int, float] = {}

    def seen(self, user_id: int, at: float) -> None:
        self._last_seen[user_id] = at

    def collect(self) -> Iterator[GaugeMetricFamily]:
        now = time.time()
        family = GaugeMetricFamily(
            "podboxbot_active_admins",
            "Distinct admins who used the bot within the window (since bot start).",
            labels=["bot", "window"],
        )
        for window, seconds in ACTIVITY_WINDOWS.items():
            active = sum(1 for at in self._last_seen.values() if now - at <= seconds)
            family.add_metric([BOT_NAME, window], active)
        yield family


class BotMetrics:
    """Все метрики бота поверх реестра SDK."""

    def __init__(self, metrics: Metrics | None = None) -> None:
        self.sdk = metrics if metrics is not None else Metrics(BOT_NAME)
        self.ledger = EpisodeLedger(None)
        registry = self.sdk.registry
        labels = ["bot"]
        self._time_to_publish = Histogram(
            "podboxbot_time_to_publish_seconds",
            "Time from receiving the episode mp3 to its first publication on a platform.",
            [*labels, "platform", "type_episode"],
            buckets=PUBLISH_BUCKETS,
            registry=registry,
        )
        self._time_to_publish_all = Histogram(
            "podboxbot_time_to_publish_all_seconds",
            "Time from receiving the episode mp3 until it is published on every platform it goes to.",
            [*labels, "type_episode"],
            buckets=PUBLISH_BUCKETS,
            registry=registry,
        )
        self._audio_size = Histogram(
            "podboxbot_episode_audio_size_bytes",
            "Size of the prepared episode mp3.",
            [*labels, "type_episode"],
            buckets=SIZE_BUCKETS,
            registry=registry,
        )
        self._audio_duration = Histogram(
            "podboxbot_episode_audio_duration_seconds",
            "Duration of the prepared episode mp3.",
            [*labels, "type_episode"],
            buckets=DURATION_BUCKETS,
            registry=registry,
        )
        self._download = Histogram(
            "podboxbot_mp3_download_seconds",
            "Time to fetch the mp3 an admin sent to the bot.",
            labels,
            buckets=DOWNLOAD_BUCKETS,
            registry=registry,
        )
        self._last_publish = Gauge(
            "podboxbot_last_publish_timestamp_seconds",
            "Unix time of the last successful publication per platform.",
            [*labels, "platform"],
            registry=registry,
        )
        self._rss_last_success = Gauge(
            "podboxbot_rss_last_success_timestamp_seconds",
            "Unix time of the last successful RSS poll.",
            labels,
            registry=registry,
        )
        self._rss_failures = Gauge(
            "podboxbot_rss_consecutive_failures",
            "RSS polls that failed in a row.",
            labels,
            registry=registry,
        )
        self._admin_last_action = Gauge(
            "podboxbot_admin_last_action_timestamp_seconds",
            "Unix time of the last admin action in the bot.",
            labels,
            registry=registry,
        )
        self._admins_configured = Gauge(
            "podboxbot_admins_configured",
            "Admins listed in ADMINS_ID.",
            labels,
            registry=registry,
        )
        self._build_info = Gauge(
            "podboxbot_build_info",
            "Running bot version (always 1).",
            [*labels, "version"],
            registry=registry,
        )
        self._activity = _AdminActivity()
        registry.register(self._activity)
        self._register_process_collectors()

    def _register_process_collectors(self) -> None:
        """Память, CPU, файлы процесса и GC Python в реестре SDK."""
        for collector in (PROCESS_COLLECTOR, PLATFORM_COLLECTOR, GC_COLLECTOR):
            try:
                self.sdk.registry.register(collector)
            except ValueError as e:
                logger.debug(f"metrics: process collector already registered: {e}")

    def use_redis(self, redis: Redis | None) -> None:
        """Подключает хранилище эпизодов; без Redis время публикации не считается."""
        self.ledger = EpisodeLedger(redis)

    @_never_fails
    def event(self, name: str, **labels: str) -> None:
        """Бизнес-событие ``sagenza_event_<name>_total`` с короткими метками."""
        self.sdk.event(name, **labels)

    @_never_fails
    def set_version(self, version: str | None) -> None:
        self._build_info.labels(BOT_NAME, version or "unknown").set(1)

    @_never_fails
    def set_admins(self, count: int) -> None:
        self._admins_configured.labels(BOT_NAME).set(count)

    @_never_fails
    def admin_seen(self, user_id: int) -> None:
        now = time.time()
        self._activity.seen(user_id, now)
        self._admin_last_action.labels(BOT_NAME).set(now)

    @_never_fails
    def admin_action(self, action: str) -> None:
        """Действие в админке или меню аудио: restart, logs, service_message, …"""
        self.sdk.event("admin_action", action=action)

    @_never_fails
    def upload_step(self, step: str, outcome: str) -> None:
        """Шаг диалога загрузки: ``outcome`` done / invalid / cancelled / expired / failed."""
        self.sdk.event("upload_step", step=step, outcome=outcome)

    @_never_fails
    def mp3_downloaded(self, seconds: float) -> None:
        self._download.labels(BOT_NAME).observe(seconds)

    @_never_fails
    async def episode_prepared(
        self,
        number: str,
        type_episode: str,
        source: str,
        received_at: float,
        size_bytes: int | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        """Готовый mp3 с меню публикации: из диалога (``upload``) или из RSS (``rss``)."""
        kind = episode_kind(type_episode)
        self.sdk.event("episode_prepared", type_episode=kind, source=source)
        if size_bytes:
            self._audio_size.labels(BOT_NAME, kind).observe(size_bytes)
        if duration_seconds:
            self._audio_duration.labels(BOT_NAME, kind).observe(duration_seconds)
        if (key := episode_number(number)) is not None:
            await self.ledger.uploaded(key, kind, received_at)

    @_never_fails
    async def publish_requested(
        self, platform: str, type_episode: str | None, number: Any = None, file_name: str | None = None
    ) -> None:
        """Нажата кнопка публикации; повторное нажатие для эпизода считается отдельно."""
        kind = episode_kind(type_episode)
        key = episode_number(number, file_name)
        count = await self.ledger.count_request(key, kind, platform) if key else 1
        attempt = "first" if count <= 1 else "repeat"
        self.sdk.event("publish_requested", platform=platform, type_episode=kind, attempt=attempt)

    @_never_fails
    def publish_request_failed(self, platform: str) -> None:
        """Запрос не ушёл в очередь публикаций (Kafka недоступна)."""
        self.sdk.event("publish_request_failed", platform=platform)

    @_never_fails
    def publish_retry(self, platform: str, stage: str | None) -> None:
        self.sdk.event("publish_retry", platform=platform, stage=stage or "unknown")

    @_never_fails
    def publish_failed(self, platform: str, type_episode: str | None, stage: str | None) -> None:
        kind = episode_kind(type_episode)
        self.sdk.event("publish_failed", platform=platform, type_episode=kind, stage=stage or "unknown")

    @_never_fails
    async def publish_succeeded(
        self,
        platform: str,
        type_episode: str | None,
        action: str | None,
        number: Any = None,
        file_name: str | None = None,
    ) -> None:
        """Эпизод опубликован (или сохранён черновиком / отложен) на площадке."""
        kind = episode_kind(type_episode)
        now = time.time()
        self.sdk.event("episode_published", platform=platform, type_episode=kind, action=action or "published")
        self._last_publish.labels(BOT_NAME, platform).set(now)

        key = episode_number(number, file_name)
        if key is None:
            return
        first, uploaded_at = await self.ledger.published(key, kind, platform, now)
        if not first or uploaded_at is None:
            return
        self._time_to_publish.labels(BOT_NAME, platform, kind).observe(now - uploaded_at)
        if await self.ledger.published_everywhere(key, kind, expected_platforms(kind)):
            self._time_to_publish_all.labels(BOT_NAME, kind).observe(now - uploaded_at)

    @_never_fails
    def rss_polled(self, result: str, failures: int) -> None:
        """Опрос ленты: ``ok``, ``not_modified`` или ``error``."""
        self.sdk.event("rss_poll", result=result)
        self._rss_failures.labels(BOT_NAME).set(failures)
        if result != "error":
            self._rss_last_success.labels(BOT_NAME).set(time.time())

    @_never_fails
    def rss_episode(self, type_episode: str | None, via: str) -> None:
        """Новый выпуск в ленте: ``via`` = bot (выложен через бота), feed (без бота), other_show."""
        kind = episode_kind(type_episode) if via != "other_show" else "unknown"
        self.sdk.event("rss_episode", type_episode=kind, via=via)

    @_never_fails
    def consumer_restarted(self, topic: str) -> None:
        self.sdk.event("kafka_consumer_restart", topic=topic)


def expected_platforms(type_episode: str | None) -> set[str]:
    """Куда эпизод этого типа выкладывается целиком.

    Основной: FTP, сайт и чат. Послешоу: FTP и включённые платные площадки
    (флаги ``<ПЛОЩАДКА>_ENABLED`` читаются на каждый вызов).
    """
    if episode_kind(type_episode) == "main":
        return {FTP, SITE, TELEGRAM}
    paid = {name for name in (BOOSTY, *PAYWALLED) if getattr(bot_config, f"{name.upper()}_ENABLED", False)}
    return {FTP, *paid}


bot_metrics = BotMetrics()
