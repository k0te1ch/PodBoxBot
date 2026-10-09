"""Остановка бота укладывается в срок, даже когда зависимость зависла.

По ``docker stop`` у процесса есть ``stop_grace_period`` секунд. Тесты держат
три вещи: обработчик остановки не ждёт зависшего клиента Kafka и задачу,
которая не реагирует на отмену; сторож завершает процесс, если тот не вышел
сам; клиент Kafka закрывается только после текущего ``poll``.
"""

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from aiogram import Dispatcher

import config
import main
from services import shutdown
from services.shutdown import Background, arm_exit_watchdog
from shared.kafka import consumer as kafka_consumer

REPO_ROOT = Path(__file__).resolve().parents[3]

# Срок в тестах в десятки раз меньше боевого: зависшее не должно его растянуть.
TIMEOUT = 0.3
SLACK = 1.0


class FakeConsumer:
    def __init__(self, topic: str, hang: threading.Event | None = None, error: Exception | None = None) -> None:
        self.topic = topic
        self.closed = False
        self._hang = hang
        self._error = error

    def close(self) -> None:
        if self._hang is not None:
            self._hang.wait()
        if self._error is not None:
            raise self._error
        self.closed = True


@pytest.fixture
def release():
    """Событие, на котором «висят» зависшие зависимости; отпускается после теста."""
    event = threading.Event()
    yield event
    event.set()


async def _forever() -> None:
    await asyncio.Event().wait()


async def _ignores_cancellation(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await stop.wait()
        except asyncio.CancelledError:
            continue


@pytest.mark.asyncio
async def test_tasks_are_cancelled_and_consumers_closed():
    background = Background()
    task = background.spawn(_forever(), name="rss-watcher")
    consumers = [FakeConsumer("publisher.ftp.result"), FakeConsumer("publisher.wordpress.result")]
    for consumer in consumers:
        background.add_consumer(consumer)

    stuck = await background.stop(TIMEOUT)

    assert stuck == []
    assert task.cancelled()
    assert all(consumer.closed for consumer in consumers)


@pytest.mark.asyncio
async def test_hung_consumer_does_not_hold_the_shutdown(release):
    """Брокер не отвечает на выход из группы: остальные клиенты закрыты, срок соблюдён."""
    background = Background()
    hung = FakeConsumer("publisher.ftp.result", hang=release)
    healthy = FakeConsumer("publisher.boosty.result")
    background.add_consumer(hung)
    background.add_consumer(healthy)

    started = time.monotonic()
    stuck = await background.stop(TIMEOUT)

    assert time.monotonic() - started < TIMEOUT + SLACK
    assert stuck == ["kafka consumer publisher.ftp.result"]
    assert healthy.closed and not hung.closed


@pytest.mark.asyncio
async def test_task_that_ignores_cancellation_does_not_hold_the_shutdown():
    background = Background()
    stop = asyncio.Event()
    stubborn = background.spawn(_ignores_cancellation(stop), name="kafka-publisher.vk.result")
    consumer = FakeConsumer("publisher.vk.result")
    background.add_consumer(consumer)
    await asyncio.sleep(0)

    started = time.monotonic()
    stuck = await background.stop(TIMEOUT)

    assert time.monotonic() - started < TIMEOUT + SLACK
    assert stuck == ["kafka-publisher.vk.result"]
    # Клиент закрыт, хотя его задача ещё не вышла.
    assert consumer.closed
    stop.set()
    await stubborn


@pytest.mark.asyncio
async def test_failed_close_is_logged_and_not_raised():
    background = Background()
    background.add_consumer(FakeConsumer("publisher.sponsr.result", error=RuntimeError("broker gone")))

    assert await background.stop(TIMEOUT) == []


@pytest.mark.asyncio
async def test_second_stop_has_nothing_to_do():
    background = Background()
    consumer = MagicMock(topic="publisher.ftp.result")
    background.add_consumer(consumer)

    await background.stop(TIMEOUT)
    await background.stop(TIMEOUT)

    consumer.close.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_handlers_finish_in_time_with_hung_dependencies(release, monkeypatch):
    """Весь путь диспетчера: зависли и клиент Kafka, и задача, а обработчики
    остановки, включая зарегистрированные позже, отработали в срок."""
    background = Background()
    stop = asyncio.Event()
    stubborn = background.spawn(_ignores_cancellation(stop), name="rss-watcher")
    background.add_consumer(FakeConsumer("publisher.ftp.result", hang=release))
    watchdogs = []
    monkeypatch.setattr(shutdown, "background", background)
    monkeypatch.setattr(shutdown, "arm_exit_watchdog", watchdogs.append)
    monkeypatch.setattr(main, "SHUTDOWN_TIMEOUT", TIMEOUT)
    called = []

    async def later_handler() -> None:
        called.append("later")

    dp = Dispatcher()
    dp.shutdown.register(main.on_shutdown)
    dp.shutdown.register(later_handler)
    await asyncio.sleep(0)

    started = time.monotonic()
    await asyncio.wait_for(dp.emit_shutdown(), timeout=TIMEOUT + SLACK)

    assert time.monotonic() - started < TIMEOUT + SLACK
    assert called == ["later"]
    # Сторож взведён на полный срок, фоновой части досталась только его доля.
    assert watchdogs == [TIMEOUT]
    stop.set()
    await stubborn


def test_bot_stops_background_work_before_the_sdk_modules():
    """Сторож взводится до обработчиков SDK: зависший модуль его не опередит.

    Раньше него только закрытие хранилища состояний, которое диспетчер
    aiogram регистрирует сам при создании.
    """
    callbacks = [handler.callback for handler in main.dp.shutdown.handlers]

    assert callbacks.index(main.on_shutdown) == 1
    assert callbacks[0].__name__ == "close"


def test_watchdog_ends_the_process_when_shutdown_hangs():
    fired = threading.Event()
    codes = []

    def exit_process(code: int) -> None:
        codes.append(code)
        fired.set()

    timer = arm_exit_watchdog(0.05, exit_process)

    assert fired.wait(SLACK)
    assert codes == [shutdown.EXIT_CODE]
    assert timer.daemon


def test_watchdog_does_not_outlive_a_normal_exit():
    """Поток-демон: штатный выход процесса сторож не задерживает."""
    exit_process = MagicMock()
    timer = arm_exit_watchdog(30, exit_process)
    try:
        assert timer.daemon
        assert timer.is_alive()
    finally:
        timer.cancel()
    exit_process.assert_not_called()


def test_shutdown_timeout_fits_into_the_container_grace_period():
    """Docker убивает процесс по истечении stop_grace_period: срок бота должен быть меньше."""
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    grace = compose["services"]["bot"]["stop_grace_period"]

    assert grace.endswith("s")
    assert config.Settings.model_fields["SHUTDOWN_TIMEOUT"].default < float(grace[:-1])


@pytest.fixture
def kafka():
    """``KafkaConsumer`` с подменённым клиентом: брокер не нужен."""
    with (
        patch.object(kafka_consumer, "Consumer") as client,
        patch.object(kafka_consumer, "SchemaRegistryClient"),
        patch.object(kafka_consumer, "AvroDeserializer"),
    ):
        yield kafka_consumer.KafkaConsumer("kafka:9092", "http://sr:8081", "publisher.ftp.result", "group"), client


def test_consumer_close_waits_for_the_poll_in_flight(kafka):
    """Клиент нельзя закрывать, пока другой поток сидит в его ``poll``."""
    consumer, client = kafka
    polling, finish_poll = threading.Event(), threading.Event()
    order = []

    def poll(_timeout: float) -> None:
        polling.set()
        finish_poll.wait(SLACK)
        order.append("poll returned")

    client.return_value.poll.side_effect = poll
    client.return_value.close.side_effect = lambda: order.append("closed")
    poller = threading.Thread(target=consumer._poll, args=(1.0,))
    poller.start()
    assert polling.wait(SLACK)

    closer = threading.Thread(target=consumer.close)
    closer.start()
    closer.join(0.1)
    assert closer.is_alive()

    finish_poll.set()
    poller.join(SLACK)
    closer.join(SLACK)
    assert order == ["poll returned", "closed"]


def test_consumer_close_is_idempotent_and_stops_polling(kafka):
    consumer, client = kafka

    consumer.close()
    consumer.close()

    client.return_value.close.assert_called_once()
    assert consumer._running is False
    assert consumer._poll(1.0) is None
    client.return_value.poll.assert_not_called()
