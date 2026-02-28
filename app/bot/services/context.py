import importlib
import inspect
from typing import Union

from loguru import logger

from config import CONTEXT_FILE
from services.none_module import _NoneModule


class _Context:

    def __init__(self, _context_obj: object) -> None:
        self._context_obj = _context_obj

    def __getattr__(self, name: str) -> Union["_Context", None, str, list, dict]:
        r = getattr(self._context_obj, name, None)

        if r is None:
            return f'"{name}" is not defined.'

        if isinstance(r, str):
            frame = inspect.currentframe()
            try:
                if (
                    frame != None
                    and frame.f_back != None
                    and frame.f_back.f_locals != None
                ):
                    caller_locals = frame.f_back.f_locals
                    r = r.format_map(caller_locals)
            finally:
                del frame

            return r

        elif isinstance(r, (list, dict)):
            return r

        elif isinstance(r, type):
            return _Context(r)

    def __getitem__(self, name: str) -> Union["_Context", None, str, list, dict]:
        r = getattr(self._context_obj, name, None)

        if r is None:
            return f'"{name}" is not defined.'

        if isinstance(r, str):
            frame = inspect.currentframe()
            try:
                if (
                    frame != None
                    and frame.f_back != None
                    and frame.f_back.f_locals != None
                ):
                    caller_locals = frame.f_back.f_locals
                    r = r.format_map(caller_locals)
            finally:
                del frame

            return r

        elif isinstance(r, (list, dict)):
            return r

        elif isinstance(r, type):
            return _Context(r)


def _get_context_obj() -> _Context | _NoneModule:
    if CONTEXT_FILE is not None:
        _module = importlib.import_module(CONTEXT_FILE)
        context = _Context(_module)
    else:
        context = _NoneModule("text", "CONTEXT_FILE")

    logger.debug("Context file loaded")
    return context
