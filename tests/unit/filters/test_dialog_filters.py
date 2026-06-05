"""Tests for the dialog-step routing filters (``filters.dialog_filters``)."""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from filters.dialog_filters import InDialog, OnStep
from forms.upload_file import MP3, TEMPLATE, TYPE_EPISODE, upload_file_engine
from utils.dialog import save_session, start_dialog


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_in_dialog_false_without_session(state):
    assert await InDialog()(None, state) is False


@pytest.mark.asyncio
async def test_in_dialog_true_with_active_session(state):
    await start_dialog(state, upload_file_engine)
    assert await InDialog()(None, state) is True


@pytest.mark.asyncio
async def test_on_step_matches_current_step_only(state):
    await start_dialog(state, upload_file_engine)  # on type_episode
    assert await OnStep(TYPE_EPISODE)(None, state) is True
    assert await OnStep(MP3)(None, state) is False


@pytest.mark.asyncio
async def test_on_step_follows_session_progress(state):
    session = await start_dialog(state, upload_file_engine)
    upload_file_engine.submit(session, "main")  # advance to mp3
    await save_session(state, session)

    assert await OnStep(TYPE_EPISODE)(None, state) is False
    assert await OnStep(MP3)(None, state) is True


@pytest.mark.asyncio
async def test_filters_false_after_dialog_completes(state):
    session = await start_dialog(state, upload_file_engine)
    upload_file_engine.submit(session, "main")
    upload_file_engine.submit(session, "file_id")
    upload_file_engine.submit(session, "Number: 1\nTitle: x\nComment: y")  # completes
    await save_session(state, session)

    assert await InDialog()(None, state) is False
    assert await OnStep(TEMPLATE)(None, state) is False
