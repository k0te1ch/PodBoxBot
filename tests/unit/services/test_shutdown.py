"""Остановка бота: хранилище состояний в Redis закрывается без ошибок.

aiogram на остановке зовёт у клиента Redis ``aclose``. В старом ``redis`` этого
метода не было: остановка падала с ``AttributeError``, а обработчики остановки,
зарегистрированные позже, уже не выполнялись.
"""

from importlib import import_module
from importlib.metadata import requires, version

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from packaging.requirements import Requirement

import main
from services.none_module import _NoneModule

# ``services.redis`` как атрибут пакета это уже готовый клиент, а нужен модуль.
redis_service = import_module("services.redis")

# Порт, на котором никто не слушает: клиент создаётся без соединения, а
# закрытие не должно его открывать.
UNUSED_REDIS_URL = "redis://127.0.0.1:1/0"


@pytest.fixture
def redis_client(monkeypatch):
    monkeypatch.setattr(redis_service, "REDIS_URL", UNUSED_REDIS_URL)
    return redis_service._get_redis_obj()


def test_storage_is_redis_when_configured(redis_client):
    storage = main._get_storage(redis_client)

    assert isinstance(storage, RedisStorage)
    assert storage.redis is redis_client


def test_storage_is_memory_without_redis():
    assert isinstance(main._get_storage(_NoneModule("redis", "REDIS_URL")), MemoryStorage)


@pytest.mark.asyncio
async def test_shutdown_closes_redis_storage_and_runs_later_handlers(redis_client):
    dp = Dispatcher(storage=main._get_storage(redis_client))
    called = []

    async def later_handler() -> None:
        called.append("later")

    dp.shutdown.register(later_handler)

    await dp.emit_shutdown()

    assert called == ["later"]


@pytest.mark.asyncio
async def test_redis_client_is_usable_after_storage_close(redis_client):
    """Клиент один на весь бот: закрытие хранилища не должно ломать его для
    тех, кто обращается к Redis позже."""
    await main._get_storage(redis_client).close()

    assert redis_client.connection_pool.connection_kwargs["decode_responses"] is True
    assert redis_client.connection_pool.make_connection() is not None


def test_installed_redis_is_within_aiogram_bounds():
    """Версия ``redis`` должна попадать в границы, которые aiogram объявляет
    для своего хранилища состояний (extra ``redis``)."""
    bounds = [
        req
        for req in map(Requirement, requires("aiogram") or [])
        if req.name == "redis" and req.marker is not None and req.marker.evaluate({"extra": "redis"})
    ]

    assert bounds, "aiogram no longer declares a redis extra"
    for req in bounds:
        assert req.specifier.contains(version("redis")), f"redis {version('redis')} is outside {req.specifier}"
