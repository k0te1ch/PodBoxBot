"""Бот и расшифровка: постановка в очередь, итог админам, подсказка по списку тем."""

import asyncio
import itertools
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Message
from fakeredis import FakeAsyncRedis

import config
import main
from handlers import transcript_handler as th
from handlers.topics_list_view import MARKED_PREFIX, REMOVE, ListCallback
from services.i18n import t
from services.topics import Author, Item, Kind, Source, runtime
from services.transcripts.requests import request_transcript, wanted
from shared.transcribe import DONE, INBOX_DIR, JOBS, Job, Result, result_key

FIXTURES = Path(__file__).parent / "fixtures"
ADMIN_ID = 1
EPISODE = (FIXTURES / "episode_reference.txt").read_text(encoding="utf-8")


@pytest.fixture
def redis(monkeypatch) -> FakeAsyncRedis:
    fake = FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(runtime, "redis", fake)
    return fake


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setattr(config, "TRANSCRIBE_ENABLED", True)
    monkeypatch.setattr(config, "TRANSCRIBE_EPISODES", "main")
    monkeypatch.setattr(config, "TOPICS_ENABLED", True)
    monkeypatch.setattr(config, "ADMINS_ID", [ADMIN_ID])
    monkeypatch.setattr("filters.dispatcher_filters.ADMINS", ["admin"])
    ticks = itertools.count(1_700_000_000)
    build = runtime.suggestion_box

    def box(*args, **kwargs):
        built = build(*args, **kwargs)
        built.clock = lambda: float(next(ticks))
        return built

    monkeypatch.setattr(runtime, "suggestion_box", box)


@pytest.fixture
def bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=7))
    bot.send_document = AsyncMock()
    return bot


async def _add(text: str, kind: Kind = Kind.TOPIC) -> Item:
    item = Item(text=text, kind=kind, author=Author(name="@listener", user_id=7), source=Source.HASHTAG)
    return await runtime.topic_list().repository.add(item, check_limits=False)


def _result(text: str = EPISODE, **kwargs) -> Result:
    job = Job(file="abc.mp3", number="767", type_episode="main")
    return Result(job, text=text, audio_seconds=3720.0, seconds=2880.0, model="small", **kwargs)


def _texts(bot) -> list[str]:
    return [call.kwargs["text"] for call in bot.send_message.await_args_list]


@pytest.mark.parametrize(
    ("enabled", "episodes", "type_episode", "expected"),
    [
        (True, "main", "main", True),
        (True, "main", "aftershow", False),
        (True, "all", "aftershow", True),
        (False, "all", "main", False),
    ],
)
def test_which_episodes_are_transcribed(monkeypatch, enabled, episodes, type_episode, expected):
    monkeypatch.setattr(config, "TRANSCRIBE_ENABLED", enabled)
    monkeypatch.setattr(config, "TRANSCRIBE_EPISODES", episodes)

    assert wanted(type_episode) is expected


def test_transcription_is_off_by_default():
    fields = config.Settings.model_fields

    assert fields["TRANSCRIBE_ENABLED"].default is False
    assert fields["TRANSCRIBE_EPISODES"].default == "main"


@pytest.mark.asyncio
async def test_prepared_mp3_is_queued_with_its_own_copy(redis, tmp_path):
    mp3 = tmp_path / "0767_rz_01102026.mp3"
    mp3.write_bytes(b"audio")

    job = await request_transcript(redis, mp3, 767, "main")

    [queued] = await redis.lrange(JOBS, 0, -1)
    assert Job.from_json(queued) == job
    assert (job.number, job.type_episode, job.file) == ("767", "main", f"{job.id}.mp3")
    copy = tmp_path / INBOX_DIR / job.file
    assert copy.read_bytes() == b"audio"
    # Следующая загрузка выпуска чистит каталог files: копия задания это переживает.
    mp3.unlink()
    assert copy.read_bytes() == b"audio"


@pytest.mark.asyncio
async def test_aftershow_is_not_queued_by_default(redis, tmp_path):
    mp3 = tmp_path / "0042_postshow_01102026.mp3"
    mp3.write_bytes(b"audio")

    assert await request_transcript(redis, mp3, 42, "aftershow") is None
    assert await redis.llen(JOBS) == 0
    assert not (tmp_path / INBOX_DIR).exists()


@pytest.mark.asyncio
async def test_admins_get_keywords_and_the_transcript_file(redis, bot, monkeypatch):
    monkeypatch.setattr(config, "TOPICS_ENABLED", False)

    await th.report(bot, _result())

    sent = bot.send_document.await_args.kwargs
    assert sent["chat_id"] == ADMIN_ID
    assert sent["caption"].startswith(t("transcript_done", episode="767", audio=62, minutes=48))
    assert "#небо" in sent["caption"] and "#отпуск" in sent["caption"]
    assert sent["document"].filename == "767_transcript.txt"
    assert sent["document"].data.decode("utf-8") == EPISODE
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_discussed_items_come_ticked_with_a_question(redis, bot):
    sky = await _add("Почему небо голубое?", Kind.QUESTION)
    await _add("Почему птицы летают?", Kind.QUESTION)
    holiday = await _add("Как съездили в отпуск")

    await th.report(bot, _result())

    listing, question = bot.send_message.await_args_list
    assert listing.kwargs["text"] == (
        "Список тем и вопросов:\n"
        f"{MARKED_PREFIX}1) <s>ВОПРОС - Почему небо голубое?</s>\n"
        "2) ВОПРОС - Почему птицы летают?\n"
        f"{MARKED_PREFIX}3) <s>ТЕМА - Как съездили в отпуск</s>"
    )
    assert question.kwargs["text"] == t("transcript_discussed", numbers="1, 3")
    remove, keep = question.kwargs["reply_markup"].inline_keyboard[0]
    assert (remove.text, keep.text) == (MARKED_PREFIX + t("transcript_remove"), t("transcript_keep"))

    # Кнопка удаления та же, что под списком: она удаляет отмеченное в показанном списке.
    view = await runtime.view_store().last(ADMIN_ID)
    assert ListCallback.unpack(remove.callback_data) == ListCallback(a=REMOVE, v=view.token)
    assert (view.marked, [view.ids[0], view.ids[2]]) == ([1, 3], [sky.id, holiday.id])


@pytest.mark.asyncio
async def test_nothing_is_suggested_when_nothing_matches(redis, bot):
    await _add("Расскажите про искусственный интеллект")

    await th.report(bot, _result())

    bot.send_document.assert_awaited_once()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_keywords_is_said_plainly(redis, bot):
    await th.report(bot, _result("Ну вот и всё на сегодня."))

    assert t("transcript_no_keywords") in bot.send_document.await_args.kwargs["caption"]


@pytest.mark.asyncio
async def test_failed_transcription_is_reported_to_admins(redis, bot):
    await th.report(bot, _result("", error="MemoryError"))

    assert _texts(bot) == [t("transcript_failed", episode="767", reason="MemoryError")]
    bot.send_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_unreachable_admin_does_not_stop_the_others(redis, bot, monkeypatch):
    monkeypatch.setattr(config, "ADMINS_ID", [5, ADMIN_ID])
    blocked = TelegramForbiddenError(method=SendMessage(chat_id=5, text="x"), message="bot was blocked by the user")
    bot.send_document.side_effect = [blocked, None]

    await th.report(bot, _result())

    assert [call.kwargs["chat_id"] for call in bot.send_document.await_args_list] == [5, ADMIN_ID]


@pytest.mark.asyncio
async def test_result_is_picked_up_from_the_done_queue(redis, bot, monkeypatch):
    result = _result()
    await redis.set(result_key(result.job.id), result.to_json())
    await redis.rpush(DONE, result.job.id)
    reported = AsyncMock()
    monkeypatch.setattr(th, "report", reported)

    watcher = asyncio.create_task(th.watch_transcripts(bot, redis, poll_seconds=1))
    try:
        async with asyncio.timeout(10):
            while not reported.await_count:
                await asyncio.sleep(0.05)
    finally:
        watcher.cancel()

    assert reported.await_args.args[1] == result
    assert await redis.llen(DONE) == 0


@pytest.mark.asyncio
async def test_lost_result_is_skipped(redis, bot, monkeypatch):
    reported = AsyncMock()
    monkeypatch.setattr(th, "report", reported)

    await th.handle_done(bot, redis, "no-such-job")

    reported.assert_not_awaited()


@pytest.mark.asyncio
async def test_keep_button_shows_the_list_without_ticks(redis, bot):
    await _add("Почему небо голубое?", Kind.QUESTION)
    await th.report(bot, _result())
    bot.send_message.reset_mock()
    question = MagicMock(spec=Message)
    question.chat = MagicMock()
    question.chat.id = ADMIN_ID
    question.chat.type = ChatType.PRIVATE
    question.edit_text = AsyncMock()
    press = MagicMock(spec=CallbackQuery)
    press.message = question
    press.from_user = MagicMock()
    press.from_user.username = "admin"
    press.answer = AsyncMock()
    assert th._admin_in_private(press)

    await th.keep_items(press, bot)

    question.edit_text.assert_awaited_once_with(t("transcript_kept"))
    assert _texts(bot) == ["Список тем и вопросов:\n1) ВОПРОС - Почему небо голубое?"]
    assert (await runtime.view_store().last(ADMIN_ID)).marked == []
    press.from_user.username = "listener"
    assert not th._admin_in_private(press)


@pytest.mark.asyncio
async def test_watcher_starts_only_when_enabled(redis, monkeypatch):
    started = MagicMock()
    monkeypatch.setattr(main, "redis", redis)
    monkeypatch.setattr(main, "watch_transcripts", started)
    monkeypatch.setattr(main.asyncio, "create_task", lambda coroutine: MagicMock())

    monkeypatch.setattr(config, "TRANSCRIBE_ENABLED", False)
    await main.start_transcript_watcher(MagicMock())
    started.assert_not_called()

    monkeypatch.setattr(config, "TRANSCRIBE_ENABLED", True)
    await main.start_transcript_watcher(MagicMock())
    started.assert_called_once()
