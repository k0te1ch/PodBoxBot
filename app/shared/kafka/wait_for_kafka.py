"""Readiness-гейты для Kafka и Schema Registry.

Зачем: после ребута хоста Docker поднимает контейнеры по `restart: always`
БЕЗ соблюдения `depends_on` (это конструкция уровня `docker compose up`, а не
рантайма демона). Значит порядок старта не гарантирован, и бот/publisher'ы
могут стартовать раньше Kafka/Schema Registry. Эти хелперы заставляют каждый
сервис дождаться зависимостей перед тем, как подписываться/публиковать —
тогда порядок старта перестаёт иметь значение.

Реализация намеренно на `confluent_kafka` (есть во ВСЕХ образах) + stdlib
`urllib` (для Schema Registry). aiokafka/requests есть не везде (Boosty и
WordPress их не тянут), поэтому импортить их в shared-код нельзя.
"""

import asyncio
import threading
import time
import urllib.request

from confluent_kafka.admin import AdminClient
from loguru import logger

_RETRY_INITIAL_DELAY = 2.0  # seconds
_RETRY_MAX_DELAY = 30.0  # seconds
# Суммарный бюджет ожидания на один заход. По истечении — RuntimeError, чтобы
# вызывающий (supervisor в боте / restart:always у publisher'а) перезапустил
# заход с чистого листа. Холодный старт Kafka на минипк (JVM + KRaft recovery)
# спокойно укладывается в этот бюджет.
_DEFAULT_TIMEOUT = 300.0  # seconds


def _check_kafka(server: str) -> bool:
    """Blocking-проба: брокер доступен и отдаёт метадату хотя бы одного брокера."""
    try:
        admin = AdminClient({"bootstrap.servers": server, "socket.timeout.ms": 4000})
        metadata = admin.list_topics(timeout=5)
        return bool(metadata and metadata.brokers)
    except Exception:
        return False


def _check_schema_registry(url: str) -> bool:
    """Blocking-проба: Schema Registry отвечает 200 на GET /subjects."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/subjects", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


async def _probe(check, target: str) -> bool:
    """Запустить blocking-пробу в daemon-потоке.

    Поток общего пула цикл при остановке дожидается (до 5 секунд на пробу), а
    daemon-поток не держит ни закрытие цикла, ни выход процесса.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()

    def _set(value: bool) -> None:
        if not future.done():
            future.set_result(value)

    def _run() -> None:
        try:
            result = check(target)
        except Exception:
            result = False
        try:
            loop.call_soon_threadsafe(_set, result)
        except RuntimeError:  # цикл уже закрыт
            pass

    threading.Thread(target=_run, name="kafka-readiness-probe", daemon=True).start()
    return await future


async def _wait(name: str, check, target: str, timeout: float) -> None:
    """Общий цикл ожидания с экспоненциальным backoff'ом до готовности/таймаута."""
    delay = _RETRY_INITIAL_DELAY
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        attempt += 1
        if await _probe(check, target):
            logger.info(f"[readiness] {name} ready ({target}) on attempt {attempt}")
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"[readiness] {name} not ready after {timeout:.0f}s ({target})")
        logger.warning(f"[readiness] {name} not ready ({target}), attempt {attempt}, retry in {delay:.0f}s")
        await asyncio.sleep(delay)
        delay = min(delay * 2, _RETRY_MAX_DELAY)


async def wait_for_kafka(kafka_server: str, timeout: float = _DEFAULT_TIMEOUT) -> None:
    await _wait("kafka", _check_kafka, kafka_server, timeout)


async def wait_for_schema_registry(schema_registry_url: str, timeout: float = _DEFAULT_TIMEOUT) -> None:
    await _wait("schema-registry", _check_schema_registry, schema_registry_url, timeout)


async def wait_for_kafka_stack(
    kafka_server: str,
    schema_registry_url: str,
    timeout: float = _DEFAULT_TIMEOUT,
) -> None:
    """Дождаться обоих: сначала брокер, потом Schema Registry (она зависит от Kafka)."""
    await wait_for_kafka(kafka_server, timeout)
    await wait_for_schema_registry(schema_registry_url, timeout)
