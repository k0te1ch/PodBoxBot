"""Схема диалога загрузки эпизода (``forms.upload_file``) без aiogram."""

import pytest
from dialog_engine import FileInfo, SessionStatus, ValidationError

from forms.upload_file import MP3, TEMPLATE, TYPE_EPISODE, resolve_text, upload_file_engine
from services.i18n import t

MP3_FILE = FileInfo(file_id="f1", mime_type="audio/mpeg", file_name="ep.mp3", file_size=1024)
TEMPLATE_TEXT = "Number: 5\nTitle: Title\nComment: Comment"


def _session(lang: str = "ru", **context):
    return upload_file_engine.create_session(context={"lang": lang, "first_name": "Ann", **context})


def test_schema_step_order_and_types():
    steps = {s.id: s for s in upload_file_engine.steps}
    assert [s.id for s in upload_file_engine.steps] == [TYPE_EPISODE, MP3, TEMPLATE]
    assert steps[TYPE_EPISODE].choices == {"main": "main_episode", "aftershow": "episode_aftershow"}
    assert steps[MP3].mime_types == ["audio/mpeg"]
    assert steps[MP3].extensions == [".mp3"]
    assert upload_file_engine.ttl is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("type_episode", ["main", "aftershow"])
async def test_full_flow_collects_answers(type_episode):
    session = _session()
    await upload_file_engine.async_submit(session, type_episode)
    await upload_file_engine.async_submit(session, [MP3_FILE])
    assert await upload_file_engine.async_submit(session, TEMPLATE_TEXT) is None

    assert session.status is SessionStatus.COMPLETED
    assert session.answers[MP3] == [MP3_FILE.to_dict()]
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
    await upload_file_engine.async_submit(session, "main")
    await upload_file_engine.async_submit(session, [MP3_FILE])
    with pytest.raises(ValidationError) as exc:
        await upload_file_engine.async_submit(session, "not a template")

    assert upload_file_engine.current_step(session).id == TEMPLATE
    assert upload_file_engine.resolve_error(exc.value, session) == t("invalid_input", "en")


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_texts_come_from_locales(lang):
    context = {"lang": lang, "first_name": "Ann", "number": "43"}
    assert "Ann" in resolve_text("ask_typeEpisode", {}, context)
    assert t("episode_aftershow", lang) in resolve_text("ask_mp3", {TYPE_EPISODE: "aftershow"}, context)
    assert "Number: 43" in resolve_text("ask_template", {TYPE_EPISODE: "main"}, context)
    assert "Chapters" not in resolve_text("ask_template", {TYPE_EPISODE: "aftershow"}, context)
    assert resolve_text("de.button.cancel", {}, context) == t("de-button-cancel", lang)


def test_unknown_service_key_falls_back_to_engine_default():
    assert resolve_text("de.button.skip", {}, {"lang": "ru"}) == "de.button.skip"
