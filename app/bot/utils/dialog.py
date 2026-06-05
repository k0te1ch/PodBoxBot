"""Glue between :mod:`dialog_engine` and aiogram's FSM storage.

``dialog_engine`` is framework-agnostic: the schema lives in a stateless
:class:`~dialog_engine.DialogEngine` and all run-time state lives in a
serialisable :class:`~dialog_engine.DialogSession`. These helpers persist that
session inside aiogram's :class:`~aiogram.fsm.context.FSMContext` (backed by
Redis in production), so a running dialog survives restarts just like the old
FSM states did.
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from dialog_engine import DialogEngine, DialogSession

# Key under which the serialised session lives in the FSM data dict.
SESSION_KEY = "dialog_session"


async def load_session(state: FSMContext, engine: DialogEngine) -> DialogSession | None:
    """Return the dialog session stored in *state*, or ``None`` if absent."""
    raw = (await state.get_data()).get(SESSION_KEY)
    if not raw:
        return None
    return engine.restore_session(raw)


async def save_session(state: FSMContext, session: DialogSession) -> None:
    """Serialise *session* back into the FSM data."""
    await state.update_data({SESSION_KEY: session.to_dict()})


async def start_dialog(state: FSMContext, engine: DialogEngine) -> DialogSession:
    """Begin a fresh dialog, replacing any session already in *state*."""
    session = engine.create_session()
    await save_session(state, session)
    return session
