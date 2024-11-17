import importlib
import inspect
import os
from typing import Any

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from config import KEYBOARDS, KEYBOARDS_DIR, KEYBOARDS_PATH
from loguru import logger


class _Keyboards:

    def __init__(self, _keyboard_obj) -> None:
        self._keyboard_obj = _keyboard_obj

    def __getattr__(self, name) -> Any:
        r = getattr(self._keyboard_obj, name, None)

        if r is None:
            return f'"{name}" is not defined.'

        if isinstance(r, str):
            frame = inspect.currentframe()
            try:
                if frame is not None and frame.f_back is not None and frame.f_back.f_locals is not None:
                    caller_locals = frame.f_back.f_locals
                    r = r.format_map(caller_locals)
            finally:
                del frame

            return r

        elif isinstance(r, (ReplyKeyboardMarkup, InlineKeyboardMarkup)):
            return r

        elif isinstance(r, type):
            return _Keyboards(r)

        return r

    def __getitem__(self, name) -> Any:
        r = getattr(self._keyboard_obj, name, None)

        if r is None:
            return f'"{name}" is not defined.'

        if isinstance(r, str):
            frame = inspect.currentframe()
            try:
                if frame is not None and frame.f_back is not None and frame.f_back.f_locals is not None:
                    caller_locals = frame.f_back.f_locals
                    r = r.format_map(caller_locals)
            finally:
                del frame

            return r

        elif isinstance(r, (ReplyKeyboardMarkup, InlineKeyboardMarkup)):
            return r

        elif isinstance(r, type):
            return _Keyboards(r)

        return r


@logger.catch
def _get_keyboards_obj() -> dict:
    keyboards = [m[:-3] for m in os.listdir(KEYBOARDS_PATH) if m.endswith(".py") and m[:-3] in KEYBOARDS]
    logger.opt(colors=True).debug(f"Loading <y>{len(keyboards)}</y> keyboards")
    tmp = {}
    for keyboard in keyboards:
        tmp[keyboard] = _Keyboards(importlib.import_module(f"{KEYBOARDS_DIR}.{keyboard}"))
        logger.opt(colors=True).debug(f"Loading <y>{keyboard}</y>...   <light-green>loaded</light-green>")
    logger.opt(colors=True).debug("Keyboards loaded")
    return tmp


keyboards: _Keyboards = _get_keyboards_obj()
