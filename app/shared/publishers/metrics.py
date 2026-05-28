"""Стандартный Prometheus-набор для publisher'ов.

Каждый publisher получает свою Registry с тремя метриками одинаковой
формы: `<name>_upload_success_total`, `<name>_upload_failure_total`,
`<name>_upload_duration_seconds`. PUSHGATEWAY-адрес и job-name
выводятся из shared.config — не требуют конфигурации subclasses.
"""
from __future__ import annotations

from aioprometheus import Counter, Summary
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
        self._duration = Summary(
            f"{name}_upload_duration_seconds",
            f"Duration of {name} upload in seconds",
            registry=self.registry,
        )
        self._pushgateway = config.PUSHGATEWAY_URL
        self._job = f"{name}_publisher"

    def success(self, labels: dict) -> None:
        self._success.inc(labels)

    def failure(self, labels: dict) -> None:
        self._failure.inc(labels)

    def duration(self, labels: dict, seconds: float) -> None:
        self._duration.observe(labels, seconds)

    async def push(self) -> None:
        """Push current registry to Pushgateway. Errors are warning-only —
        broken metrics must never take down a publisher."""
        try:
            pusher = Pusher(job_name=self._job, addr=self._pushgateway)
            await pusher.add(registry=self.registry)
            logger.debug(f"Metrics pushed to Pushgateway for {self.name}")
        except Exception as e:
            logger.warning(f"Failed to push metrics for {self.name}: {e}")
