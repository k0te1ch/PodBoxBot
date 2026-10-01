"""Стандартный Prometheus-набор для publisher'ов.

Каждый publisher получает свою Registry с метриками одинаковой формы
(``<name>`` это имя publisher'а: ftp, wp, boosty, vk, patreon, sponsr):

* ``<name>_upload_success_total``, ``<name>_upload_failure_total`` и
  ``<name>_upload_duration_seconds`` с меткой ``target`` (ключ эпизода);
* ``<name>_upload_retry_total`` по ``target`` и шагу (``stage``);
* ``<name>_upload_error_total`` по шагу и классу исключения (``error``);
* ``<name>_last_success_timestamp_seconds`` — время последней удачной публикации;
* ``<name>_session_*`` — состояние авторизации на площадке, если оно есть
  (Boosty: когда истекает токен, удалось ли его проверить и обновить).

PUSHGATEWAY-адрес и job-name выводятся из shared.config — не требуют
конфигурации subclasses.
"""

from __future__ import annotations

import time

from aioprometheus import Counter, Gauge, Summary
from aioprometheus.collectors import Registry
from aioprometheus.pusher import Pusher
from loguru import logger

from shared.config import config


class PublisherMetrics:
    """Per-publisher prometheus surface + push helper."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.registry = Registry()
        self._success = Counter(
            f"{name}_upload_success_total",
            f"Total successful {name} uploads",
            registry=self.registry,
        )
        self._failure = Counter(
            f"{name}_upload_failure_total",
            f"Total failed {name} uploads",
            registry=self.registry,
        )
        self._retry = Counter(
            f"{name}_upload_retry_total",
            f"Failed {name} attempts that were retried",
            registry=self.registry,
        )
        self._duration = Summary(
            f"{name}_upload_duration_seconds",
            f"Duration of {name} upload in seconds",
            registry=self.registry,
        )
        self._error = Counter(
            f"{name}_upload_error_total",
            f"Failed {name} uploads by step and exception class",
            registry=self.registry,
        )
        self._last_success = Gauge(
            f"{name}_last_success_timestamp_seconds",
            f"Unix time of the last successful {name} upload",
            registry=self.registry,
        )
        self._session_ok = Gauge(
            f"{name}_session_ok",
            f"1 if the last {name} session check succeeded, 0 otherwise",
            registry=self.registry,
        )
        self._session_expires_at = Gauge(
            f"{name}_session_expires_at_timestamp_seconds",
            f"Unix time when the current {name} access token expires",
            registry=self.registry,
        )
        self._session_refresh = Counter(
            f"{name}_session_refresh_total",
            f"{name} session checks and token refreshes by result",
            registry=self.registry,
        )
        self._pushgateway = config.PUSHGATEWAY_URL
        self._job = f"{name}_publisher"

    def success(self, labels: dict) -> None:
        self._success.inc(labels)
        self._last_success.set({}, time.time())

    def failure(self, labels: dict) -> None:
        self._failure.inc(labels)

    def retry(self, labels: dict) -> None:
        self._retry.inc(labels)

    def duration(self, labels: dict, seconds: float) -> None:
        self._duration.observe(labels, seconds)

    def error(self, stage: str, error: str) -> None:
        """Публикация упала на шаге ``stage`` с исключением класса ``error``."""
        self._error.inc({"stage": stage, "error": error})

    def session(self, ok: bool, expires_at: float | None = None) -> None:
        """Итог проверки авторизации на площадке и срок жизни токена."""
        self._session_ok.set({}, 1 if ok else 0)
        self._session_refresh.inc({"result": "ok" if ok else "error"})
        if expires_at:
            self._session_expires_at.set({}, expires_at)

    async def push(self) -> None:
        """Push current registry to Pushgateway. Errors are warning-only —
        broken metrics must never take down a publisher."""
        try:
            pusher = Pusher(job_name=self._job, addr=self._pushgateway)
            await pusher.add(registry=self.registry)
            logger.debug(f"Metrics pushed to Pushgateway for {self.name}")
        except Exception as e:
            logger.warning(f"Failed to push metrics for {self.name}: {e}")
