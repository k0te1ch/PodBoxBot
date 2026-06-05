"""Shared fixtures for the podcast_handler dialog tests.

The handlers were migrated from an aiogram ``StatesGroup`` to the
``dialog_engine`` library: the per-user progress now lives in a serialised
:class:`~dialog_engine.DialogSession` stored in the FSM data under
``utils.dialog.SESSION_KEY`` instead of in aiogram's ``state``.

``aiogram_tests`` only injects ``state_data`` into storage when a non-empty
``state`` is also supplied (see ``TelegramEventObserverHandler.__call__``), so
tests pass the :func:`dialog_state` sentinel purely to trigger that injection —
the handlers themselves no longer read the aiogram state.
"""

from collections.abc import Callable

import pytest

from forms.upload_file import MP3, TEMPLATE, TYPE_EPISODE, upload_file_engine
from utils.dialog import SESSION_KEY

# Sentinel aiogram state used only so aiogram_tests writes our state_data.
_DIALOG_STATE = "uploading"


@pytest.fixture
def dialog_state() -> str:
    """Sentinel FSM state that makes aiogram_tests persist ``state_data``."""
    return _DIALOG_STATE


@pytest.fixture
def session_state_data() -> Callable[..., dict]:
    """Factory building FSM ``state_data`` with a session on a given step.

    Steps are reached by replaying the real engine transitions, so the session's
    history/answers are exactly what production would have produced.
    """

    def _make(*, step: str = TYPE_EPISODE, type_episode: str = "main") -> dict:
        session = upload_file_engine.create_session()
        if step in (MP3, TEMPLATE):
            upload_file_engine.submit(session, type_episode)  # type_episode -> mp3
        if step == TEMPLATE:
            upload_file_engine.submit(session, "stub_file_id")  # mp3 -> template
        return {SESSION_KEY: session.to_dict()}

    return _make
