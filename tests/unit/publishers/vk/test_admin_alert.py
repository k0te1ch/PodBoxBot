"""Алерты админам: дедупликация, отправка всем чатам, мягкая обработка ошибок."""

import httpx
import pytest
from app.publishers.VK.admin_alert import AdminAlerts


def _alerts(handler, chat_ids=(1, 2), **kw):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AdminAlerts("bottoken", chat_ids, http=http, **kw)


@pytest.mark.asyncio
async def test_sends_to_all_admins_once():
    sent = []

    def handler(request):
        sent.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"ok": True})

    alerts = _alerts(handler)
    assert await alerts.send("key", "текст") is True
    assert [s["chat_id"] for s in sent] == ["1", "2"]
    assert sent[0]["text"] == "текст"


@pytest.mark.asyncio
async def test_same_key_is_not_repeated_within_window():
    calls = []
    clock = [1000.0]

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"ok": True})

    alerts = _alerts(handler, chat_ids=(1,), repeat_after=3600, clock=lambda: clock[0])
    assert await alerts.send("k", "a") is True
    assert await alerts.send("k", "a") is False  # слишком рано
    clock[0] += 3601
    assert await alerts.send("k", "a") is True
    assert sum(calls) == 2


@pytest.mark.asyncio
async def test_forget_lets_key_send_again():
    def handler(request):
        return httpx.Response(200, json={"ok": True})

    alerts = _alerts(handler, chat_ids=(1,))
    await alerts.send("vk-reauth", "a")
    assert await alerts.send("vk-reauth", "a") is False
    alerts.forget("vk-")
    assert await alerts.send("vk-reauth", "a") is True


@pytest.mark.asyncio
async def test_disabled_without_token_or_chats():
    alerts = AdminAlerts(None, [1])
    assert alerts.enabled is False
    assert await alerts.send("k", "a") is False


@pytest.mark.asyncio
async def test_telegram_error_does_not_raise():
    def handler(request):
        return httpx.Response(500, json={"ok": False})

    alerts = _alerts(handler, chat_ids=(1,))
    assert await alerts.send("k", "a") is False  # не упало, просто не доставлено
    # ключ не запомнен как отправленный — повтор возможен
    assert "k" not in alerts._sent
