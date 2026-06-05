"""Tests for the aiogram <-> dialog_engine glue in ``utils.dialog``."""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from forms.upload_file import MP3, TYPE_EPISODE, upload_file_engine
from utils.dialog import SESSION_KEY, load_session, save_session, start_dialog


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_load_session_returns_none_when_empty(state):
    assert await load_session(state, upload_file_engine) is None


@pytest.mark.asyncio
async def test_start_dialog_creates_and_persists_session(state):
    session = await start_dialog(state, upload_file_engine)

    assert upload_file_engine.current_step(session).id == TYPE_EPISODE
    assert SESSION_KEY in (await state.get_data())

    restored = await load_session(state, upload_file_engine)
    assert restored is not None
    assert upload_file_engine.current_step(restored).id == TYPE_EPISODE


@pytest.mark.asyncio
async def test_save_session_round_trips_progress(state):
    session = await start_dialog(state, upload_file_engine)
    upload_file_engine.submit(session, "main")  # advance to mp3
    await save_session(state, session)

    restored = await load_session(state, upload_file_engine)
    assert restored.answers[TYPE_EPISODE] == "main"
    assert upload_file_engine.current_step(restored).id == MP3


@pytest.mark.asyncio
async def test_save_session_preserves_other_fsm_data(state):
    await state.update_data(unrelated="keep-me")
    session = await start_dialog(state, upload_file_engine)
    await save_session(state, session)

    data = await state.get_data()
    assert data["unrelated"] == "keep-me"
    assert SESSION_KEY in data
