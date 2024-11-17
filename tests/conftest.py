import pytest
import asyncio
from loguru import logger
import logging


@pytest.fixture(scope="function")
def event_loop():
    """Создаёт новый цикл событий для каждого теста"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Перенаправление логов loguru в caplog
@pytest.fixture(autouse=True, scope="function")
def loguru_caplog(caplog):
    class PropagateHandler(logging.Handler):
        def emit(self, record):
            logging.getLogger(record.name).handle(record)

    logger.remove()  # Убираем все существующие логгеры loguru
    logger.add(PropagateHandler(), format="{message}")
    yield
    logger.remove()
