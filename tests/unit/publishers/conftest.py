"""Общие фикстуры publisher-тестов: без пауз между ретраями и без сети в verify."""

from unittest.mock import AsyncMock

import pytest


async def _no_sleep(_delay: float) -> None:
    return None


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    from shared.publishers import base

    monkeypatch.setattr(base.BasePublisher, "retry_sleep", staticmethod(_no_sleep))


@pytest.fixture(autouse=True)
def verify_published_mock(monkeypatch):
    """verify_published по умолчанию считает пост доступным."""
    from shared.publishers import base

    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(base, "verify_published", mock)
    return mock
