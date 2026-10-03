"""Диалог загрузки эпизода в хендлерах: /new, кнопки, MP3, шаблон.

Хендлеры вызываются напрямую с настоящим FSMContext на MemoryStorage и
ботом-заглушкой: так видно, что именно раннер DialogEngine отправил и что
осталось в хранилище.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from dialog_engine import FileInfo
from dialog_engine.integrations.aiogram import DialogTurn

from forms.upload_file import MP3, TEMPLATE, TYPE_EPISODE, upload_file_engine
from handlers import podcast_handler
from services.i18n import t
from utils.ftp_methods import EpisodeNumberError

CHAT_ID = 100
STEP_MESSAGE_ID = 7


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=CHAT_ID, user_id=CHAT_ID))


@pytest.fixture
def bot() -> MagicMock:
    bot = MagicMock()
    sent = MagicMock(message_id=STEP_MESSAGE_ID)
    sent.chat.id = CHAT_ID
    bot.send_message = AsyncMock(return_value=sent)
    bot.edit_message_text = AsyncMock()
    bot.edit_message_reply_markup = AsyncMock()
    return bot


def _message(text: str | None = None, **media) -> MagicMock:
    msg = MagicMock(text=text, audio=None, document=None, photo=None, video=None, voice=None, animation=None)
    msg.video_note = None
    for name, value in media.items():
        setattr(msg, name, value)
    msg.chat.id = CHAT_ID
    msg.from_user.first_name = "Ann"
    msg.reply = AsyncMock()
    msg.answer = AsyncMock()
    return msg


def _callback(data: str) -> MagicMock:
    callback = MagicMock(data=data)
    callback.message.chat.id = CHAT_ID
    callback.message.edit_text = AsyncMock()
    callback.message.answer = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    callback.answer = AsyncMock()
    return callback


def _buttons(markup) -> dict[str, str]:
    return {b.text: b.callback_data for row in markup.inline_keyboard for b in row}


async def _session(state: FSMContext):
    session, _ui = await podcast_handler.storage.load(state)
    return session


async def _start(state, bot, language="ru"):
    await podcast_handler.new_episode(_message("/new"), state, bot, language)
    return _buttons(bot.send_message.call_args.kwargs["reply_markup"])


async def _choose(state, bot, language="ru", type_episode="main"):
    buttons = await _start(state, bot, language)
    label = t("main_episode" if type_episode == "main" else "episode_aftershow", language)
    await podcast_handler.on_dialog_button(_callback(buttons[label]), state, bot, language, "admin")


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["ru", "en"])
async def test_start_asks_episode_type_with_inline_buttons(state, bot, language):
    buttons = await _start(state, bot, language)

    assert bot.send_message.call_args.kwargs["text"] == t("ask_typeEpisode", language)
    assert {t("main_episode", language), t("episode_aftershow", language), t("de-button-cancel", language)} <= set(
        buttons
    )
    assert upload_file_engine.current_step(await _session(state)).id == TYPE_EPISODE


@pytest.mark.asyncio
@pytest.mark.parametrize("type_episode", ["main", "aftershow"])
async def test_choosing_type_moves_to_mp3_step(state, bot, type_episode):
    await _choose(state, bot, type_episode=type_episode)

    session = await _session(state)
    assert session.answers[TYPE_EPISODE] == type_episode
    assert upload_file_engine.current_step(session).id == MP3
    label = t("main_episode" if type_episode == "main" else "episode_aftershow")
    assert label in bot.edit_message_text.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_cancel_button_cancels_the_dialog(state, bot):
    buttons = await _start(state, bot)
    callback = _callback(buttons[t("de-button-cancel")])

    await podcast_handler.on_dialog_button(callback, state, bot, "ru", "admin")

    assert await _session(state) is None
    callback.message.edit_text.assert_awaited_once_with(t("canceled"))


@pytest.mark.asyncio
async def test_cancel_command_cancels_the_dialog(state, bot):
    await _start(state, bot)
    msg = _message("/cancel")

    await podcast_handler.cancel(msg, state, bot, "ru", "admin")

    assert await _session(state) is None
    msg.reply.assert_awaited_once_with(t("canceled"))
    bot.edit_message_reply_markup.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_mp3_file_is_rejected_without_download(state, bot):
    await _choose(state, bot)
    document = MagicMock(file_id="doc", mime_type="application/pdf", file_name="a.pdf", file_size=10)

    with patch.object(podcast_handler, "_download_mp3", new=AsyncMock()) as download:
        await podcast_handler.get_MP3(_message(document=document), state, bot, "ru", "admin")

    download.assert_not_awaited()
    assert upload_file_engine.current_step(await _session(state)).id == MP3
    assert "⚠️" in bot.edit_message_text.call_args.kwargs["text"]


@pytest.fixture
def mp3_message() -> MagicMock:
    audio = MagicMock(file_id="audio", mime_type="audio/mpeg", file_name="ep.mp3", file_size=2048)
    msg = _message(audio=audio)
    msg.reply = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    return msg


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["ru", "en"])
async def test_mp3_is_downloaded_and_template_asked_with_next_number(state, bot, mp3_message, language):
    await _choose(state, bot, language)
    bot.send_message.reset_mock()

    with (
        patch.object(podcast_handler, "clear_old_mp3_files", new=AsyncMock()),
        patch.object(podcast_handler, "_download_mp3", new=AsyncMock(return_value=True)) as download,
        patch.object(podcast_handler, "get_last_post_id", new=AsyncMock(return_value=42)),
    ):
        await podcast_handler.get_MP3(mp3_message, state, bot, language, "admin")

    download.assert_awaited_once()
    assert download.call_args.args[0] == FileInfo("audio", "audio/mpeg", "ep.mp3", 2048)
    mp3_message.reply.assert_awaited_once_with(t("got_mp3", language))
    mp3_message.reply.return_value.edit_text.assert_awaited_once_with(t("downloaded", language))

    # Шаблон — новым сообщением, с номером следующего эпизода.
    assert "Number: 43" in bot.send_message.call_args.kwargs["text"]
    session = await _session(state)
    assert upload_file_engine.current_step(session).id == TEMPLATE
    assert session.context["number"] == "43"


@pytest.mark.asyncio
async def test_failed_download_cancels_the_dialog(state, bot, mp3_message):
    await _choose(state, bot)

    with (
        patch.object(podcast_handler, "clear_old_mp3_files", new=AsyncMock()),
        patch.object(podcast_handler, "_download_mp3", new=AsyncMock(return_value=False)),
    ):
        await podcast_handler.get_MP3(mp3_message, state, bot, "ru", "admin")

    mp3_message.reply.return_value.edit_text.assert_awaited_once_with(t("download_failed"))
    assert await _session(state) is None


@pytest.mark.asyncio
async def test_ftp_failure_on_episode_number_is_reported_and_closes_the_dialog(state, bot, mp3_message):
    await _choose(state, bot)
    bot.edit_message_reply_markup.reset_mock()
    failure = EpisodeNumberError("error_perm: 530 <Login incorrect>")

    with (
        patch.object(podcast_handler, "clear_old_mp3_files", new=AsyncMock()),
        patch.object(podcast_handler, "_download_mp3", new=AsyncMock(return_value=True)),
        patch.object(podcast_handler, "get_last_post_id", new=AsyncMock(side_effect=failure)),
    ):
        await podcast_handler.get_MP3(mp3_message, state, bot, "ru", "admin")

    # Раньше исключение уходило в общий обработчик: админ не получал ответа,
    # а диалог висел на шаге MP3.
    mp3_message.reply.return_value.edit_text.assert_awaited_once_with(
        t("episode_number_failed", error="error_perm: 530 &lt;Login incorrect&gt;")
    )
    assert await _session(state) is None
    bot.edit_message_reply_markup.assert_awaited_once()


async def _on_template_step(state, bot, mp3_message):
    await _choose(state, bot)
    with (
        patch.object(podcast_handler, "clear_old_mp3_files", new=AsyncMock()),
        patch.object(podcast_handler, "_download_mp3", new=AsyncMock(return_value=True)),
        patch.object(podcast_handler, "get_last_post_id", new=AsyncMock(return_value=42)),
    ):
        await podcast_handler.get_MP3(mp3_message, state, bot, "ru", "admin")


@pytest.mark.asyncio
async def test_invalid_template_keeps_the_step(state, bot, mp3_message):
    await _on_template_step(state, bot, mp3_message)

    with patch.object(podcast_handler, "publish_episode", new=AsyncMock()) as publish:
        await podcast_handler.set_template(_message("garbage"), state, bot, "ru", "admin")

    publish.assert_not_awaited()
    assert t("invalid_input") in bot.edit_message_text.call_args.kwargs["text"]
    assert upload_file_engine.current_step(await _session(state)).id == TEMPLATE


@pytest.mark.asyncio
async def test_valid_template_finishes_and_publishes(state, bot, mp3_message):
    await _on_template_step(state, bot, mp3_message)
    msg = _message("Number: 43\nTitle: Title\nComment: Comment")

    with patch.object(podcast_handler, "publish_episode", new=AsyncMock()) as publish:
        await podcast_handler.set_template(msg, state, bot, "ru", "admin")

    turn: DialogTurn = publish.call_args.args[1]
    assert turn.answers[TYPE_EPISODE] == "main"
    assert turn.answers[TEMPLATE]["number"] == "43"
    assert await _session(state) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("type_episode", ["main", "aftershow"])
async def test_publish_episode_tags_and_sends_audio_with_menu(tmp_path, type_episode):
    podcast = tmp_path / "podcast.mp3"
    podcast.write_bytes(b"mp3")
    msg = _message()
    msg.answer = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
    msg.reply_audio = AsyncMock()
    turn = DialogTurn(finished=True, answers={TYPE_EPISODE: type_episode, TEMPLATE: {"number": "42", "title": "T"}})
    markup = MagicMock()

    with (
        patch.object(podcast_handler, "FILES_PATH", tmp_path),
        patch.object(podcast_handler, "PODCAST_PATH", podcast),
        patch.object(podcast_handler, "audio_tag") as audio_tag,
        patch.object(podcast_handler, "read_duration_and_artist", return_value=(1, "A")),
        patch.object(podcast_handler, "save_template_info", new=AsyncMock()),
        patch.object(podcast_handler, "audio_menu_markup", new=AsyncMock(return_value=markup)) as menu,
    ):
        await podcast_handler.publish_episode(msg, turn, "ru", "admin")

    audio_tag.assert_called_once_with(turn.answers[TEMPLATE], type_episode)
    menu.assert_awaited_once_with(msg, type_episode)
    kwargs = msg.reply_audio.call_args.kwargs
    assert kwargs["caption"] == t("done_mp3")
    assert kwargs["reply_markup"] is markup
    assert list(Path(tmp_path).glob("0042_*.mp3"))


@pytest.mark.asyncio
async def test_menu_button_turns_the_menu_into_the_first_question(state, bot):
    """«Новый выпуск» правит сообщение меню, а не шлёт новое: чат не дёргается."""
    menu_message = _message()
    menu_message.message_id = 55

    await podcast_handler.start_upload(state, bot, menu_message, "ru")

    bot.send_message.assert_not_awaited()
    edited = bot.edit_message_text.call_args.kwargs
    assert (edited["chat_id"], edited["message_id"], edited["text"]) == (CHAT_ID, 55, t("ask_typeEpisode"))
    assert upload_file_engine.current_step(await _session(state)).id == TYPE_EPISODE


@pytest.mark.asyncio
async def test_mp3_without_a_dialog_starts_the_episode(state, bot, mp3_message):
    """Присланный mp3 сам начинает выпуск: бот спрашивает тип, файл повторять не надо."""
    await podcast_handler.mp3_without_dialog(mp3_message, state, bot, "ru", "admin")

    assert bot.send_message.call_args.kwargs["text"] == t("ask_typeEpisode_for_file")
    buttons = _buttons(bot.send_message.call_args.kwargs["reply_markup"])
    session = await _session(state)
    assert upload_file_engine.current_step(session).id == TYPE_EPISODE
    bot.send_message.reset_mock()

    callback = _callback(buttons[t("main_episode")])
    with (
        patch.object(podcast_handler, "clear_old_mp3_files", new=AsyncMock()),
        patch.object(podcast_handler, "_download_mp3", new=AsyncMock(return_value=True)) as download,
        patch.object(podcast_handler, "get_last_post_id", new=AsyncMock(return_value=42)),
    ):
        await podcast_handler.on_dialog_button(callback, state, bot, "ru", "admin")

    assert download.call_args.args[0] == FileInfo("audio", "audio/mpeg", "ep.mp3", 2048)
    callback.message.answer.assert_awaited_once_with(t("got_mp3"))
    assert "Number: 43" in bot.send_message.call_args.kwargs["text"]
    assert upload_file_engine.current_step(await _session(state)).id == TEMPLATE


@pytest.mark.asyncio
async def test_other_file_without_a_dialog_gets_a_hint(state, bot):
    document = MagicMock(file_id="doc", mime_type="application/pdf", file_name="a.pdf", file_size=10)
    msg = _message(document=document)

    await podcast_handler.mp3_without_dialog(msg, state, bot, "ru", "admin")

    msg.reply.assert_awaited_once_with(t("file_not_mp3"))
    assert await _session(state) is None
    bot.send_message.assert_not_awaited()


@pytest.fixture
def funnel():
    """Шаги диалога, которые хендлеры отдали в метрики: (step, outcome)."""
    steps: list[tuple[str, str]] = []
    with patch.object(podcast_handler.bot_metrics, "upload_step", side_effect=lambda s, o: steps.append((s, o))):
        yield steps


@pytest.mark.asyncio
async def test_funnel_counts_passed_steps(state, bot, mp3_message, funnel):
    await _on_template_step(state, bot, mp3_message)

    assert funnel == [("start", "done"), (TYPE_EPISODE, "done"), (MP3, "done")]


@pytest.mark.asyncio
async def test_funnel_marks_rejected_template_and_where_the_admin_cancelled(state, bot, mp3_message, funnel):
    await _on_template_step(state, bot, mp3_message)
    with patch.object(podcast_handler, "publish_episode", new=AsyncMock()):
        await podcast_handler.set_template(_message("garbage"), state, bot, "ru", "admin")
    await podcast_handler.cancel(_message("/cancel"), state, bot, "ru", "admin")

    assert funnel[-2:] == [(TEMPLATE, "invalid"), (TEMPLATE, "cancelled")]


@pytest.mark.asyncio
async def test_funnel_marks_failed_download(state, bot, mp3_message, funnel):
    await _choose(state, bot)
    with (
        patch.object(podcast_handler, "clear_old_mp3_files", new=AsyncMock()),
        patch.object(podcast_handler, "_download_mp3", new=AsyncMock(return_value=False)),
    ):
        await podcast_handler.get_MP3(mp3_message, state, bot, "ru", "admin")

    assert funnel[-1] == (MP3, "download_failed")
