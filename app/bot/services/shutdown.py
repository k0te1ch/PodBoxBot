"""Остановка бота, ограниченная по времени.

По ``docker stop`` у процесса есть ``stop_grace_period`` секунд, потом Docker
убивает его (код 137). Раньше остановку ничто не ограничивало:

* фоновые задачи (шесть слушателей Kafka, опрос RSS) никто не отменял, их
  снимал уже ``asyncio.run`` на выходе и ждал без срока;
* клиенты Kafka никто не закрывал: каждый закрывался сам при сборке мусора,
  по очереди, с выходом из группы и ожиданием брокера;
* зависший поток (FTP, теги mp3, проверка Kafka) держал выход процесса.

Теперь всё это делается явно и со сроком:

1. до обработчиков остановки SDK взводится сторож: если процесс не вышел
   за ``SHUTDOWN_TIMEOUT``, он завершает его сам, с записью в журнал;
2. фоновые задачи отменяются, на завершение у них часть срока;
3. клиенты Kafka закрываются одновременно, каждый в своём потоке-демоне:
   зависшее закрытие не мешает ни остальным, ни выходу процесса.
"""

import asyncio
import os
import threading
from collections.abc import Callable, Coroutine
from contextlib import suppress
from typing import Any, Protocol

from loguru import logger

EXIT_CODE = 1
"""Код выхода, когда процесс завершил сторож, а не штатная остановка."""

BACKGROUND_SHARE = 0.6
"""Доля срока на фоновые задачи и клиенты Kafka. Остальное остаётся модулям
SDK, закрытию сессии Telegram и выходу интерпретатора."""

TASKS_SHARE = 0.4
"""Доля срока фоновой части на отмену задач; остальное на закрытие клиентов."""


class Closable(Protocol):
    topic: str

    def close(self) -> None: ...


class Background:
    """Фоновые задачи и клиенты Kafka, которые надо остановить вместе с ботом."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._consumers: list[Closable] = []

    def spawn(self, coro: Coroutine[Any, Any, Any], name: str) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def add_consumer(self, consumer: Closable) -> None:
        self._consumers.append(consumer)

    async def stop(self, timeout: float) -> list[str]:
        """Отменяет задачи и закрывает клиенты не дольше ``timeout`` секунд.

        Возвращает имена тех, кто не уложился: они остаются как есть, ждать
        их дальше незачем.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        stuck = await self._cancel_tasks(timeout * TASKS_SHARE)
        stuck += await self._close_consumers(max(deadline - loop.time(), 0.0))
        if stuck:
            logger.warning(f"shutdown: gave up waiting for {', '.join(stuck)}")
        return stuck

    async def _cancel_tasks(self, timeout: float) -> list[str]:
        tasks = list(self._tasks)
        if not tasks:
            return []
        for task in tasks:
            task.cancel()
        _, pending = await asyncio.wait(tasks, timeout=timeout)
        return [task.get_name() for task in pending]

    async def _close_consumers(self, timeout: float) -> list[str]:
        consumers, self._consumers = self._consumers, []
        if not consumers:
            return []
        closing = {_close_in_thread(consumer): consumer.topic for consumer in consumers}
        done, pending = await asyncio.wait(closing, timeout=timeout)
        for future in done:
            if (error := future.exception()) is not None:
                logger.warning(f"shutdown: consumer for {closing[future]} was not closed cleanly: {error!r}")
        return [f"kafka consumer {closing[future]}" for future in pending]


def _close_in_thread(consumer: Closable) -> asyncio.Future[None]:
    """Закрывает клиент в потоке-демоне: поток, зависший на брокере, не
    держит ни цикл событий, ни выход процесса (в отличие от ``to_thread``)."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[None] = loop.create_future()

    def resolve(error: BaseException | None) -> None:
        if future.done():
            return
        if error is None:
            future.set_result(None)
        else:
            future.set_exception(error)

    def run() -> None:
        error: BaseException | None = None
        try:
            consumer.close()
        except Exception as caught:
            error = caught
        # Цикл событий мог закрыться, пока закрытие висело.
        with suppress(RuntimeError):
            loop.call_soon_threadsafe(resolve, error)

    threading.Thread(target=run, name=f"close-{consumer.topic}", daemon=True).start()
    return future


def arm_exit_watchdog(timeout: float, exit_process: Callable[[int], Any] = os._exit) -> threading.Timer:
    """Завершает процесс, если тот не вышел сам за ``timeout`` секунд.

    Таймер живёт в потоке-демоне: при штатном выходе он просто исчезает.
    ``os._exit`` не ждёт ни потоков, ни деструкторов, поэтому срабатывает и
    тогда, когда интерпретатор уже завис на выходе.
    """

    def fire() -> None:
        logger.error(f"shutdown: not finished in {timeout:g}s, exiting without waiting for the rest")
        exit_process(EXIT_CODE)

    timer = threading.Timer(timeout, fire)
    timer.daemon = True
    timer.name = "shutdown-watchdog"
    timer.start()
    return timer


background = Background()
"""Фоновые задачи и клиенты Kafka этого процесса."""


async def stop_bot(timeout: float) -> None:
    """Обработчик остановки диспетчера. Регистрируется раньше модулей SDK:
    сторож должен быть взведён до того, как они начнут останавливаться."""
    arm_exit_watchdog(timeout)
    await background.stop(timeout * BACKGROUND_SHARE)
