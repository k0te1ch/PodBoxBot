"""Статус-сообщение долгой операции: шаги, прогресс и частота правок."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from services.i18n import t
from utils import status_message
from utils.status_message import StatusMessage, bar, human_seconds, human_size, progress_detail

MB = 1024 * 1024


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def bot() -> MagicMock:
    return MagicMock(edit_message_text=AsyncMock())


@pytest.fixture
def status(bot, clock) -> StatusMessage:
    return StatusMessage(bot, 1, 2, "Выпуск", ["download", "number"], clock=clock)


def _texts(bot) -> list[str]:
    return [call.kwargs["text"] for call in bot.edit_message_text.call_args_list]


def test_sizes_and_times_read_like_a_person_wrote_them():
    assert human_size(27.44 * MB) == "27,4 МБ"
    assert human_size(27.44 * MB, "en") == "27.4 MB"
    assert human_size(2048) == "2 КБ"
    assert human_seconds(40) == "40 с"
    assert human_seconds(125) == "2 мин 05 с"
    assert bar(0.45) == "▰▰▰▰▱▱▱▱▱▱"
    assert bar(2) == "▰" * 10


def test_progress_shows_percent_size_and_time_left():
    assert progress_detail(10 * MB, 40 * MB, elapsed=10) == "25% ▰▰▱▱▱▱▱▱▱▱ 10,0 из 40,0 МБ, ещё ~30 с"
    # В самом начале оценки времени ещё нет: она была бы случайной.
    assert progress_detail(10 * MB, 40 * MB, elapsed=1) == "25% ▰▰▱▱▱▱▱▱▱▱ 10,0 из 40,0 МБ"
    assert progress_detail(40 * MB, 40 * MB, elapsed=10).startswith("100% ")


@pytest.mark.asyncio
async def test_steps_are_shown_with_marks(status, bot):
    await status.begin("download")
    await status.done("download", "27,4 МБ")
    await status.begin("number")

    assert _texts(bot)[-1] == "\n".join(
        ["<b>Выпуск</b>", f"✅ {t('status_download_done')} · 27,4 МБ", f"⏳ {t('status_number')}"]
    )


@pytest.mark.asyncio
async def test_progress_is_not_sent_more_often_than_the_interval(status, bot, clock):
    """Telegram ограничивает частоту правок: промежуточные идут не чаще раза в две секунды."""
    await status.begin("download")
    for megabytes in range(1, 11):
        clock.now += 0.5
        await status.progress("download", megabytes * MB, 10 * MB)

    # Начало шага и две правки за пять секунд, а не десять.
    assert bot.edit_message_text.await_count == 3
    clock.now += 0.1
    await status.done("download")
    assert bot.edit_message_text.await_count == 4


@pytest.mark.asyncio
async def test_long_step_without_progress_shows_how_long_it_takes(status, bot, clock):
    await status.begin("number")
    clock.now += 12
    await status.update()
    assert _texts(bot)[-1].endswith(f"⏳ {t('status_number')} · 12 с")

    clock.now += 60
    await status.update()
    assert t("status_slow", time="1 мин 12 с") in _texts(bot)[-1]


@pytest.mark.asyncio
async def test_failure_stays_in_the_message(status, bot):
    await status.begin("download")
    await status.fail("download", "не скачался")

    assert _texts(bot)[-1].split("\n")[1] == f"❌ {t('status_download')} · не скачался"


@pytest.mark.asyncio
async def test_flood_limit_drops_progress_but_not_the_result(status, bot, clock, monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(status_message.asyncio, "sleep", sleep)
    flood = TelegramRetryAfter(method=MagicMock(), message="Too Many Requests", retry_after=7)
    await status.begin("download")

    bot.edit_message_text.side_effect = flood
    clock.now += 3
    await status.progress("download", MB, 10 * MB)
    sleep.assert_not_awaited()
    # Пока Telegram просит подождать, новых попыток нет.
    clock.now += 3
    await status.progress("download", 2 * MB, 10 * MB)
    assert bot.edit_message_text.await_count == 2

    bot.edit_message_text.side_effect = [flood, None]
    await status.done("download")
    sleep.assert_awaited_once_with(7)
    assert f"✅ {t('status_download_done')}" in _texts(bot)[-1]


@pytest.mark.asyncio
async def test_unchanged_text_is_not_an_error(status, bot):
    bot.edit_message_text.side_effect = TelegramBadRequest(MagicMock(), "message is not modified")

    await status.begin("download")
    await status.begin("download")

    assert bot.edit_message_text.await_count == 1
