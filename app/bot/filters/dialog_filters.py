"""aiogram filters that route messages by the active dialog step.

These replace the aiogram ``StateFilter`` / ``StatesGroup`` membership checks.
Routing decisions are delegated to :mod:`dialog_engine`: a message reaches a
handler only when the user's :class:`~dialog_engine.DialogSession` is active and
sitting on the expected step.
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject
from dialog_engine import DialogEngine

from forms.upload_file import upload_file_engine
from utils.dialog import load_session


class InDialog(BaseFilter):
    """Pass when the user has an active dialog session (on any step)."""

    def __init__(self, engine: DialogEngine = upload_file_engine) -> None:
        self.engine = engine

    async def __call__(self, _event: TelegramObject, state: FSMContext) -> bool:
        session = await load_session(state, self.engine)
        return session is not None and session.is_active


class OnStep(BaseFilter):
    """Pass when the active dialog session is currently on ``step_id``."""

    def __init__(self, step_id: str, engine: DialogEngine = upload_file_engine) -> None:
        self.step_id = step_id
        self.engine = engine

    async def __call__(self, _event: TelegramObject, state: FSMContext) -> bool:
        session = await load_session(state, self.engine)
        if session is None or not session.is_active:
            return False
        current = self.engine.current_step(session)
        return current is not None and current.id == self.step_id
