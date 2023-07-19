import importlib
import inspect
import os
import re

from config import CONTEXT_FILE

from loguru import logger

#TODO здесь где-то ошибка, при которой не выводиться ask_template
class _Context(object):
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
        
        elif isinstance(r, list):
            return r
        
        elif isinstance(r, dict):
            return r

        elif isinstance(r, type):
            return _Context(r)

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
        
        elif isinstance(r, list):
            return r
        
        elif isinstance(r, dict):
            return r

        elif isinstance(r, type):
            return _Context(r)
        
class _NotDefinedModule(Exception):
    pass


class _NoneModule(object):
    def __init__(self, module_name, attr_name):
        self.module_name = module_name
        self.attr_name = attr_name

    def __getattr__(self, attr):
        msg = f"You are using {self.module_name} while the {self.attr_name} is not set in config"
        logger.critical(msg)
        raise _NotDefinedModule(msg)


def _get_context_obj():
    if CONTEXT_FILE is not None:
        _module = importlib.import_module(CONTEXT_FILE)
        context = _Context(_module)
    else:
        context = _NoneModule("text", "CONTEXT_FILE")

    logger.debug("Context file loaded")
    return context

context = _get_context_obj()