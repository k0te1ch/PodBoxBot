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
    monkeypatch.setattr(main._publisher, "producer", MagicMock(send=AsyncMock()))
    monkeypatch.setattr(main._publisher, "_session_ok", None)
    monkeypatch.setattr(main, "BOOSTY_BLOG", "podbox")
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


def _sent_states(publisher):
    return [(call.args[1]["event_type"], call.args[1]["status"]) for call in publisher.producer.send.await_args_list]


@pytest.mark.asyncio
async def test_lost_login_is_reported_to_the_bot_once(publisher):
    from app.publishers.Boosty import main

    publisher.client.ensure_auth.side_effect = main.BoostyAuthError("refresh_token отклонён")

    await publisher._check_session()
    await publisher._check_session()

    assert _sent_states(publisher) == [("session", "failure")]
    event = publisher.producer.send.await_args.args[1]
    assert "refresh_token отклонён" in event["error"]


@pytest.mark.asyncio
async def test_restored_login_is_reported_after_a_failure(publisher):
    from app.publishers.Boosty import main

    publisher.client.ensure_auth.side_effect = main.BoostyAuthError("refresh_token отклонён")
    await publisher._check_session()
    publisher.client.ensure_auth.side_effect = None
    await publisher._check_session()

    assert _sent_states(publisher) == [("session", "failure"), ("session", "success")]


@pytest.mark.asyncio
async def test_network_error_is_not_reported_as_a_lost_login(publisher):
    publisher.client.ensure_auth.side_effect = ConnectionError("boosty is down")

    await publisher._check_session()

    publisher.producer.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_unconfigured_boosty_reports_nothing(publisher, monkeypatch):
    from app.publishers.Boosty import main

    monkeypatch.setattr(main, "BOOSTY_BLOG", "")
    publisher.client.ensure_auth.side_effect = main.BoostyAuthError("BOOSTY_BLOG не задан")

    await publisher._check_session()

    publisher.producer.send.assert_not_awaited()
