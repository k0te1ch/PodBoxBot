"""Событие ``session`` от публишера Boosty: одно сообщение админам на поломку и на восстановление."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis import FakeAsyncRedis

from services.boosty_session import DOWN_KEY, on_session_event
from services.i18n import t

FAILURE = {"event_type": "session", "status": "failure", "error": "Boosty: refresh_token отклонён"}
SUCCESS = {"event_type": "session", "status": "success"}


@pytest.fixture
def bot():
    return MagicMock(send_message=AsyncMock())


@pytest.fixture
def redis():
    return FakeAsyncRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_lost_login_is_reported_to_every_admin_once(bot, redis):
    await on_session_event(FAILURE, bot, redis, [1, 2], "ru")
    await on_session_event(FAILURE, bot, redis, [1, 2], "ru")

    assert [call.args[0] for call in bot.send_message.await_args_list] == [1, 2]
    assert "refresh_token отклонён" in bot.send_message.await_args.args[1]
    assert await redis.get(DOWN_KEY) == "1"


@pytest.mark.asyncio
async def test_restored_login_is_reported_only_after_a_failure(bot, redis):
    await on_session_event(SUCCESS, bot, redis, [1], "ru")
    bot.send_message.assert_not_awaited()

    await on_session_event(FAILURE, bot, redis, [1], "ru")
    await on_session_event(SUCCESS, bot, redis, [1], "ru")

    assert bot.send_message.await_args.args == (1, t("boosty_session_restored"))
    assert await redis.get(DOWN_KEY) is None


@pytest.mark.asyncio
async def test_failed_send_to_one_admin_does_not_stop_the_others(bot, redis):
    bot.send_message.side_effect = [RuntimeError("blocked"), None]

    await on_session_event(FAILURE, bot, redis, [1, 2], "ru")

    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_router_sends_session_events_to_the_admins(bot, redis, monkeypatch):
    import config
    from services.kafka.handlers import upload_event

    monkeypatch.setattr(config, "ADMINS_ID", [7])
    monkeypatch.setattr("services.redis", redis)
    monkeypatch.setattr("services.telegram_updater", MagicMock(bot=bot))

    await upload_event.router.route(FAILURE)

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.args[0] == 7
