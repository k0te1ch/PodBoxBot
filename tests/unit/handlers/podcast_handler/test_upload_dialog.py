"""Диалог загрузки эпизода в хендлерах: /new, кнопки, MP3, шаблон.

Хендлеры вызываются напрямую с настоящим FSMContext на MemoryStorage и
ботом-заглушкой: так видно, что именно раннер DialogEngine отправил и что
осталось в хранилище.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from dialog_engine import FileInfo
from dialog_engine.integrations.aiogram import DialogTurn

from forms.upload_file import MP3, TEMPLATE, TYPE_EPISODE, upload_file_engine
from handlers import podcast_handler
from services.i18n import t
from utils.ftp_methods import EpisodeNumberError
from utils.status_message import human_size

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
    bot.send_chat_action = AsyncMock()
    return bot


STATUS_MESSAGE_ID = 21


def _edits(bot, message_id=STATUS_MESSAGE_ID) -> list[str]:
    """Тексты, которыми бот правил сообщение, по порядку."""
    return [
        call.kwargs["text"] for call in bot.edit_message_text.call_args_list if call.kwargs["message_id"] == message_id
    ]


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
    callback.message.answer = AsyncMock(return_value=MagicMock(message_id=STATUS_MESSAGE_ID))
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
    msg.reply = AsyncMock(return_value=MagicMock(message_id=STATUS_MESSAGE_ID))
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
    # Одно сообщение на всё: ответ на файл, шаги загрузки и вопрос про описание.
    mp3_message.reply.assert_awaited_once_with(t("got_mp3", language))
    bot.send_message.assert_not_awaited()
    edits = _edits(bot)
    assert f"⏳ {t('status_download', language)}" in edits[0]
    assert f"✅ {t('status_download_done', language)} · {human_size(2048, language)}" in edits[1]
    assert f"⏳ {t('status_number', language)}" in edits[2]
    assert "Number: 43" in edits[-1]
    assert t("downloaded", language, size=human_size(2048, language), number="43") in edits[-1]
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

    assert f"❌ {t('status_download')} · {t('download_failed')}" in _edits(bot)[-1]
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
    last = _edits(bot)[-1]
    assert f"✅ {t('status_download_done')}" in last
    assert t("episode_number_failed", error="error_perm: 530 &lt;Login incorrect&gt;") in last
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


def _publish_message(bot) -> MagicMock:
    msg = _message()
    msg.bot = bot
    msg.answer = AsyncMock(return_value=MagicMock(message_id=STATUS_MESSAGE_ID))
    msg.answer_audio = AsyncMock()
    bot.edit_message_media = AsyncMock()
    return msg


@pytest.fixture
def episode_files(tmp_path):
    podcast = tmp_path / "podcast.mp3"
    podcast.write_bytes(b"mp3")
    with (
        patch.object(podcast_handler, "FILES_PATH", tmp_path),
        patch.object(podcast_handler, "PODCAST_PATH", podcast),
        patch.object(podcast_handler, "read_duration_and_artist", return_value=(1, "A")),
        patch.object(podcast_handler, "save_template_info", new=AsyncMock()),
        patch.object(podcast_handler, "audio_menu_markup", new=AsyncMock(return_value=MagicMock())) as menu,
    ):
        yield tmp_path, menu


def _turn(type_episode="main") -> DialogTurn:
    return DialogTurn(finished=True, answers={TYPE_EPISODE: type_episode, TEMPLATE: {"number": "42", "title": "T"}})


@pytest.mark.asyncio
@pytest.mark.parametrize("type_episode", ["main", "aftershow"])
async def test_publish_episode_tags_and_turns_the_status_into_the_audio(bot, episode_files, type_episode):
    """Статус не удаляется: то же сообщение становится готовым файлом с меню."""
    tmp_path, menu = episode_files
    msg = _publish_message(bot)
    turn = _turn(type_episode)

    with patch.object(podcast_handler, "audio_tag") as audio_tag:
        await podcast_handler.publish_episode(msg, turn, "ru", "admin")

    audio_tag.assert_called_once_with(turn.answers[TEMPLATE], type_episode)
    menu.assert_awaited_once_with(msg, type_episode)
    title = t("status_episode_title", number="42", title="T")
    msg.answer.assert_awaited_once_with(f"<b>{title}</b>")
    edits = _edits(bot)
    assert f"⏳ {t('status_tags')}" in edits[0]
    assert f"✅ {t('status_tags_done')}" in edits[-1]
    assert f"⏳ {t('status_send')}" in edits[-1]
    replaced = bot.edit_message_media.call_args.kwargs
    assert replaced["message_id"] == STATUS_MESSAGE_ID
    assert replaced["media"].caption == t("done_mp3")
    assert replaced["reply_markup"] is menu.return_value
    msg.answer_audio.assert_not_awaited()
    msg.answer.return_value.delete.assert_not_called()
    assert list(Path(tmp_path).glob("0042_*.mp3"))


@pytest.mark.asyncio
async def test_audio_is_sent_apart_when_the_status_cannot_become_a_file(bot, episode_files):
    _tmp_path, menu = episode_files
    msg = _publish_message(bot)
    bot.edit_message_media = AsyncMock(side_effect=TelegramBadRequest(MagicMock(), "message can't be edited"))

    with patch.object(podcast_handler, "audio_tag"):
        await podcast_handler.publish_episode(msg, _turn(), "ru", "admin")

    assert msg.answer_audio.call_args.kwargs["reply_markup"] is menu.return_value
    assert f"✅ {t('status_send_done')}" in _edits(bot)[-1]


@pytest.mark.asyncio
async def test_failed_tagging_is_reported_in_the_status(bot, episode_files):
    msg = _publish_message(bot)

    with patch.object(podcast_handler, "audio_tag", side_effect=RuntimeError("no <cover>")):
        await podcast_handler.publish_episode(msg, _turn(), "ru", "admin")

    assert t("status_tags_failed", error="no &lt;cover&gt;") in _edits(bot)[-1]
    bot.edit_message_media.assert_not_awaited()


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
    bot.send_message.assert_not_awaited()
    assert "Number: 43" in _edits(bot)[-1]
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
