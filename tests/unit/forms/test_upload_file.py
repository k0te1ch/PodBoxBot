"""Tests for the upload-episode dialog schema (``forms.upload_file``).

These exercise the ``dialog_engine`` schema directly — step order, the choice
constraint, media collection, completion and round-trip serialisation — so the
contract the handlers rely on is pinned independently of aiogram.
"""

import pytest
from dialog_engine import DialogSession, SessionStatus, ValidationError

from forms.upload_file import MP3, TEMPLATE, TYPE_EPISODE, upload_file_engine


def test_schema_step_order_and_types():
    steps = upload_file_engine.steps
    assert [s.id for s in steps] == [TYPE_EPISODE, MP3, TEMPLATE]
    by_id = {s.id: s for s in steps}
    assert by_id[TYPE_EPISODE].type == "choice"
    assert by_id[TYPE_EPISODE].choices == {"main": "main_episode", "aftershow": "episode_aftershow"}
    assert by_id[MP3].type == "file"
    assert by_id[TEMPLATE].type == "text"


def test_first_step_is_type_episode():
    session = upload_file_engine.create_session()
    assert upload_file_engine.current_step(session).id == TYPE_EPISODE
    assert session.is_active


@pytest.mark.parametrize("type_episode", ["main", "aftershow"])
def test_full_happy_path(type_episode):
    session = upload_file_engine.create_session()

    nxt = upload_file_engine.submit(session, type_episode)
    assert nxt.id == MP3
    assert session.answers[TYPE_EPISODE] == type_episode

    nxt = upload_file_engine.submit(session, "audio_file_id")
    assert nxt.id == TEMPLATE
    assert session.answers[MP3] == ["audio_file_id"]  # file step normalises to a list

    nxt = upload_file_engine.submit(session, "Number: 1\nTitle: x\nComment: y")
    assert nxt is None  # dialog complete
    assert session.status == SessionStatus.COMPLETED


def test_invalid_episode_type_is_rejected():
    session = upload_file_engine.create_session()
    with pytest.raises(ValidationError):
        upload_file_engine.submit(session, "not-a-choice")
    # Session stays on the first step so the user can retry.
    assert upload_file_engine.current_step(session).id == TYPE_EPISODE


def test_session_survives_serialisation_round_trip():
    session = upload_file_engine.create_session()
    upload_file_engine.submit(session, "main")

    restored = DialogSession.from_dict(session.to_dict())
    assert restored.answers == session.answers
    assert upload_file_engine.current_step(restored).id == MP3
