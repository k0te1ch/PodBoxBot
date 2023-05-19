import logging
import os
import re
import click
import inspect
import importlib

from aiogram import Bot, Dispatcher, executor
from aiogram.bot.api import TelegramAPIServer
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.fsm_storage.redis import RedisStorage2

MAIN_MODULE_NAME = os.path.basename(__file__)[:-3]

try:
    from settings import TOKEN, SKIP_UPDATES, PARSE_MODE, HANDLERS_DIR, MODELS_DIR, \
        CONTEXT_FILE, HANDLERS, LOCALSERVER
except ModuleNotFoundError:
    click.echo(click.style(
        "Config file not found!\n"
        "Please create config.py file according to config.py.example",
        fg='bright_red'))
    exit()
except ImportError as err:
    var = re.match(r"cannot import name '(\w+)' from", err.msg).groups()[0]
    click.echo(click.style(
        f"{var} is not defined in the config file",
        fg='bright_red'))
    exit()


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
        raise _NotDefinedModule(msg)


def _get_bot_obj():
    server = TelegramAPIServer.from_base('http://localhost') if LOCALSERVER else TelegramAPIServer.from_base('https://api.telegram.org')
    bot = Bot(
        token=TOKEN,
        parse_mode=PARSE_MODE,
        server=server
    )
    return bot


def _get_dp_obj(bot):
    storage = MemoryStorage()
    dp = Dispatcher(bot, storage=storage)

    return dp


def _get_context_obj():
    if CONTEXT_FILE is not None:
        _module = importlib.import_module(CONTEXT_FILE)
        context = _Context(_module)
    else:
        context = _NoneModule("text", "CONTEXT_FILE")

    return context

__all__ = [
    "bot",
    "db",
    "context",
]


if __name__ == MAIN_MODULE_NAME:
    bot = _get_bot_obj()
    dp = _get_dp_obj(bot)
    context = _get_context_obj()


if __name__ == '__main__':
    from cli import cli
    cli()
