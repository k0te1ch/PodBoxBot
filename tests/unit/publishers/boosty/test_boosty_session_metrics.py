"""Состояние авторизации Boosty в метриках: жив ли токен и когда истекает."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def publisher(monkeypatch):
    from app.publishers.Boosty import main

    client = MagicMock(expires_at=1_900_000_000)
    client.ensure_auth = AsyncMock()
    monkeypatch.setattr(main._publisher, "client", client)
    monkeypatch.setattr(main._publisher.metrics, "push", AsyncMock())
    return main._publisher


@pytest.mark.asyncio
async def test_successful_auth_reports_token_expiry(publisher):
    await publisher._check_session()

    assert publisher.metrics._session_ok.get({}) == 1
    assert publisher.metrics._session_expires_at.get({}) == 1_900_000_000
    publisher.metrics.push.assert_awaited()


@pytest.mark.asyncio
async def test_rejected_token_is_reported_and_publication_still_fails(publisher):
    from app.publishers.Boosty.boosty_auth import BoostyAuthError

    publisher.client.ensure_auth.side_effect = BoostyAuthError("refresh_token отклонён")

    await publisher._check_session()
    assert publisher.metrics._session_ok.get({}) == 0

    with pytest.raises(BoostyAuthError):
        await publisher._ensure_auth()
