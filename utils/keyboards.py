import importlib
import inspect
import os
import re

from config import KEYBOARDS, KEYBOARDS_DIR

from loguru import logger

class _Keyboards(object):
    def __init__(self, _context_obj):
        self._context_obj = _context_obj

    def __getattr__(self, name):
        r = getattr(self._context_obj, name, None)

        if r is None:
            return f"\"{name}\" is not defined."

        if isinstance(r, str):
            frame = inspect.currentframe()
            try:
                caller_locals = frame.f_back.f_locals
                r = r.format_map(caller_locals)
            finally:
                del frame

            return r
        elif isinstance(r, type):
            return _Keyboards(r)
        return r

    def __getitem__(self, name):
        r = getattr(self._context_obj, name, None)

        if r is None:
            return f"\"{name}\" is not defined."

        if isinstance(r, str):
            frame = inspect.currentframe()
            try:
                caller_locals = frame.f_back.f_locals
                r = r.format_map(caller_locals)
            finally:
                del frame

            return r
        elif isinstance(r, type):
            return _Keyboards(r)
        return r
    

@logger.catch
def _get_keyboards_obj():
    keyboards = [m[:-3] for m in os.listdir(KEYBOARDS_DIR) if m.endswith(".py") and m[:-3] in KEYBOARDS]
    logger.opt(colors=True).debug(f"Loading <y>{len(keyboards)}</y> keyboards")
    tmp = {}
    for keyboard in keyboards:
        tmp[keyboard] = _Keyboards(importlib.import_module(f'{KEYBOARDS_DIR}.{keyboard}'))
        logger.opt(colors=True).debug(f"Loading <y>{keyboard}</y>...   <light-green>loaded</light-green>")
    logger.opt(colors=True).debug(f"Keyboards loaded")
    return tmp

keyboards = _get_keyboards_obj()