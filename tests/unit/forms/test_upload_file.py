"""Схема диалога загрузки эпизода (``forms.upload_file``) без aiogram."""

from datetime import datetime

import pytest
from dialog_engine import FileInfo, SessionStatus, ValidationError

from forms import upload_file
from forms.upload_file import (
    MP3,
    PUBLISH_AT,
    RECORDING_DATE,
    TEMPLATE,
    TYPE_EPISODE,
    resolve_text,
    upload_file_engine,
)
from services.i18n import t

MP3_FILE = FileInfo(file_id="f1", mime_type="audio/mpeg", file_name="ep.mp3", file_size=1024)
TEMPLATE_TEXT = "Number: 5\nTitle: Title\nComment: Comment"


NOW = datetime(2026, 10, 3, 14, 30)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(upload_file, "now", lambda: NOW)


async def _to_template(session, type_episode="main", recorded="2026-10-02", publish="default"):
    await upload_file_engine.async_submit(session, type_episode)
    await upload_file_engine.async_submit(session, [MP3_FILE])
    await upload_file_engine.async_submit(session, recorded)
    await upload_file_engine.async_submit(session, publish)


def _session(lang: str = "ru", **context):
    return upload_file_engine.create_session(context={"lang": lang, "first_name": "Ann", **context})


def test_schema_step_order_and_types():
    steps = {s.id: s for s in upload_file_engine.steps}
    assert [s.id for s in upload_file_engine.steps] == [TYPE_EPISODE, MP3, RECORDING_DATE, PUBLISH_AT, TEMPLATE]
    assert steps[TYPE_EPISODE].choices == {"main": "main_episode", "aftershow": "episode_aftershow"}
    assert steps[MP3].mime_types == ["audio/mpeg"]
    assert steps[MP3].extensions == [".mp3"]
    assert upload_file_engine.ttl is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("type_episode", ["main", "aftershow"])
async def test_full_flow_collects_answers(type_episode):
    session = _session()
    await _to_template(session, type_episode, publish="2026-10-05T2000")
    assert await upload_file_engine.async_submit(session, TEMPLATE_TEXT) is None

    assert session.status is SessionStatus.COMPLETED
    assert session.answers[MP3] == [MP3_FILE.to_dict()]
    assert session.answers[RECORDING_DATE] == "2026-10-02"
    assert session.answers[PUBLISH_AT] == "2026-10-05T20:00"
    assert session.answers[TEMPLATE]["number"] == "5"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file",
    [
        FileInfo(file_id="f", mime_type="audio/ogg", file_name="ep.ogg", file_size=10),
        FileInfo(file_id="f", mime_type="audio/mpeg", file_name="ep.wav", file_size=10),
        FileInfo(file_id="f", mime_type="audio/mpeg", file_name="ep.mp3", file_size=None),
    ],
)
async def test_mp3_step_rejects_other_files(file):
    session = _session()
    await upload_file_engine.async_submit(session, "main")
    with pytest.raises(ValidationError):
        await upload_file_engine.async_submit(session, [file])
    assert upload_file_engine.current_step(session).id == MP3


@pytest.mark.asyncio
async def test_bad_template_keeps_the_step_with_translated_error():
    session = _session(lang="en")
    await _to_template(session)
    with pytest.raises(ValidationError) as exc:
        await upload_file_engine.async_submit(session, "not a template")

    assert upload_file_engine.current_step(session).id == TEMPLATE
    assert upload_file_engine.resolve_error(exc.value, session) == t("invalid_input", "en")


@pytest.mark.asyncio
async def test_bad_recording_date_gets_its_own_error():
    session = _session(lang="en")
    await _to_template(session)
    with pytest.raises(ValidationError) as exc:
        await upload_file_engine.async_submit(
            session, "Number: 1\nRecording Date: 31.31.2026\nTitle: Header\nComment: Comment"
        )

    assert upload_file_engine.current_step(session).id == TEMPLATE
    assert upload_file_engine.resolve_error(exc.value, session) == t("invalid_recording_date", "en")


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_texts_come_from_locales(lang):
    context = {"lang": lang, "number": "43"}
    assert resolve_text("ask_typeEpisode", {}, context) == t("ask_typeEpisode", lang)
    with_file = {**context, "pending_mp3": {"file_id": "audio"}}
    assert resolve_text("ask_typeEpisode", {}, with_file) == t("ask_typeEpisode_for_file", lang)
    assert t("episode_aftershow", lang) in resolve_text("ask_mp3", {TYPE_EPISODE: "aftershow"}, context)
    assert "Number: 43" in resolve_text("ask_template", {TYPE_EPISODE: "main"}, context)
    assert "Chapters" not in resolve_text("ask_template", {TYPE_EPISODE: "aftershow"}, context)
    assert resolve_text("de.button.cancel", {}, context) == t("de-button-cancel", lang)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("typed", "stored"),
    [("2026-10-03", "2026-10-03"), ("02.10.2026", "2026-10-02"), ("1/9/2026", "2026-09-01")],
)
async def test_recording_date_comes_from_a_button_or_typed_text(typed, stored):
    session = _session()
    await upload_file_engine.async_submit(session, "main")
    await upload_file_engine.async_submit(session, [MP3_FILE])
    await upload_file_engine.async_submit(session, typed)

    assert session.answers[RECORDING_DATE] == stored
    assert upload_file_engine.current_step(session).id == PUBLISH_AT


@pytest.mark.asyncio
@pytest.mark.parametrize("typed", ["2026-10-04", "04.10.2026", "вчера"])
async def test_recording_date_from_the_future_or_unreadable_is_refused(typed):
    session = _session()
    await upload_file_engine.async_submit(session, "main")
    await upload_file_engine.async_submit(session, [MP3_FILE])
    with pytest.raises(ValidationError) as exc:
        await upload_file_engine.async_submit(session, typed)

    assert upload_file_engine.current_step(session).id == RECORDING_DATE
    assert upload_file_engine.resolve_error(exc.value, session) == t("invalid_recording_date")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("default", ""),
        ("2026-10-03T2000", "2026-10-03T20:00"),
        ("05.10.2026 19:30", "2026-10-05T19:30"),
        ("05.10.2026   9:05", "2026-10-05T09:05"),
        ("05.10.2026 1930", "2026-10-05T19:30"),
    ],
)
async def test_publication_time_is_optional(typed, stored):
    session = _session()
    await upload_file_engine.async_submit(session, "main")
    await upload_file_engine.async_submit(session, [MP3_FILE])
    await upload_file_engine.async_submit(session, "2026-10-03")
    await upload_file_engine.async_submit(session, typed)

    assert session.answers[PUBLISH_AT] == stored
    assert upload_file_engine.current_step(session).id == TEMPLATE


async def _to_publish_at(**context):
    session = _session(**context)
    await upload_file_engine.async_submit(session, "main")
    await upload_file_engine.async_submit(session, [MP3_FILE])
    await upload_file_engine.async_submit(session, "2026-10-03")
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("typed", ["05.10.2026", "завтра", "25:00", "19:75", "вечером в семь"])
async def test_publication_that_is_not_a_time_is_refused_with_an_example(typed):
    session = await _to_publish_at()
    with pytest.raises(ValidationError) as exc:
        await upload_file_engine.async_submit(session, typed)

    assert upload_file_engine.current_step(session).id == PUBLISH_AT
    error = upload_file_engine.resolve_error(exc.value, session)
    assert error == t("invalid_publish_at")
    assert "19:30" in error and "05.10.2026 20:00" in error


@pytest.mark.asyncio
@pytest.mark.parametrize("typed", ["2026-10-03T1200", "02.10.2026 20:00", "14:30", "9:00", "1200"])
async def test_publication_in_the_past_is_refused_with_the_current_time(typed):
    """Сейчас 14:30: время, которое сегодня уже прошло, бот не берёт и на
    завтра сам не переносит."""
    session = await _to_publish_at()
    with pytest.raises(ValidationError) as exc:
        await upload_file_engine.async_submit(session, typed)

    assert upload_file_engine.current_step(session).id == PUBLISH_AT
    assert upload_file_engine.resolve_error(exc.value, session) == t("publish_time_passed", now="14:30")


@pytest.mark.asyncio
@pytest.mark.parametrize("typed", ["19:30", "19.30", "1930", "19 30"])
async def test_typed_time_without_a_day_means_today(typed):
    session = await _to_publish_at()

    await upload_file_engine.async_submit(session, typed)

    assert session.answers[PUBLISH_AT] == "2026-10-03T19:30"
    assert upload_file_engine.current_step(session).id == TEMPLATE


@pytest.mark.asyncio
async def test_typed_time_goes_to_the_day_picked_with_a_button():
    """День выбран кнопкой, время набрано: утро выбранного дня ещё впереди,
    хотя сегодня этот час уже прошёл."""
    session = await _to_publish_at(publish_day="2026-10-05")

    await upload_file_engine.async_submit(session, "9.05")

    assert session.answers[PUBLISH_AT] == "2026-10-05T09:05"
    assert "publish_day" not in session.context


def test_questions_keep_what_is_already_known_about_the_episode():
    context = {"lang": "ru", "number": "43", "mp3_size": "27,4 МБ"}
    answers = {TYPE_EPISODE: "main", RECORDING_DATE: "2026-10-02", PUBLISH_AT: "2026-10-05T20:00"}

    assert resolve_text("ask_recording_date", {}, context) == (
        "✅ Файл получен (27,4 МБ), это будет выпуск 43\n\nКогда записывали выпуск?"
    )
    assert resolve_text("ask_publish_at", answers, context).startswith("Выпуск 43 · запись 2 октября\n\n")
    template = resolve_text("ask_template", answers, context)
    assert template.startswith("Выпуск 43 · запись 2 октября · публикация 5 октября, 20:00\n\n")
    assert "Recording Date" not in template
    usual = resolve_text("ask_template", {**answers, PUBLISH_AT: ""}, context)
    assert "публикация как обычно" in usual


def test_unknown_service_key_falls_back_to_engine_default():
    assert resolve_text("de.button.skip", {}, {"lang": "ru"}) == "de.button.skip"
