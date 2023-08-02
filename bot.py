import importlib
import inspect
import os
import re

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from handlers import podcastHandler, admin_panel
from handlers.middlewares import GeneralMiddleware

# LOGGER
try:
    from config import LOG_LEVEL
except:
    LOG_LEVEL = "INFO"
import sys

from loguru import logger

logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format=
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level>::<blue>{module}</blue>::<cyan>{function}</cyan>::<cyan>{line}</cyan> | <level>{message}</level>",
    level=LOG_LEVEL,
    backtrace=True,
    diagnose=True)

MODULE_PATH = os.path.dirname(os.path.realpath(__file__))
if not os.path.exists(f"{MODULE_PATH}/logs"):
    os.mkdir(f"{MODULE_PATH}/logs")
logger.add(
    MODULE_PATH + "/logs/file_{time:YYYY-MM-DD_HH-mm-ss}.log",
    rotation="5 MB",
    format=
    "{time:YYYY-MM-DD HH:mm:ss} | {level}::{module}::{function}::{line} | {message}",
    level="TRACE",
    backtrace=True,
    diagnose=True)

# IMPORT SETTINGS
MAIN_MODULE_NAME = os.path.basename(__file__)[:-3]

try:
    from config import (ADMINS, API_TOKEN, CONTEXT_FILE, DATABASE,
                        DATABASE_URL, ENABLE_APSCHEDULER, KEYBOARDS,
                        KEYBOARDS_DIR, MODELS_DIR, PARSE_MODE, PROXY,
                        PROXY_AUTH, REDIS_URL, SKIP_UPDATES, TG_SERVER)
    logger.debug("Loading settings from config")
except ModuleNotFoundError:
    logger.critical(
        "Config file not found! Please create config.py file according to config.py.example"
    )
    exit()
except ImportError as err:
    var = re.match(r"cannot import name '(\w+)' from", err.msg).groups()[0]
    logger.critical(f"{var} is not defined in the config file")
    exit()

# OBJECTS FOR BOT


class _SQLAlchemy(object):

    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        self.Model = declarative_base()

        self.sessionmaker = sessionmaker(bind=self.engine)
        self.session = scoped_session(self.sessionmaker)

        self.Model.query = self.session.query_property()

    @property
    def metadata(self):
        return self.Model.metadata


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


# GET TG BOT OBJECT
def _get_bot_obj():
    from config import TG_SERVER, LOCAL
    #TODO CHECK THIS
    if TG_SERVER == None and LOCAL:
        from aiogram.client.telegram import TelegramAPIServer
        from aiogram.client.session.aiohttp import AiohttpSession
        TG_SERVER = AiohttpSession(
            api=TelegramAPIServer.from_base('http://localhost:8081'))
        logger.opt(colors=True).info(
            f"Telegram bot configured for work with custom server <light-blue>({TG_SERVER.api.base[:TG_SERVER.api.base.find('/bot')]})</light-blue>"
        )
    elif TG_SERVER != None:
        from aiogram.client.telegram import TelegramAPIServer
        from aiogram.client.session.aiohttp import AiohttpSession
        TG_SERVER = AiohttpSession(api=TelegramAPIServer.from_base(TG_SERVER))
        logger.opt(colors=True).info(
            f"Telegram bot configured for work with custom server <light-blue>({TG_SERVER.api.base[:TG_SERVER.api.base.find('/bot')]})</light-blue>"
        )
    else:
        logger.opt(colors=True).debug(
            f"The standard api tg server is used"  # TODO подкорректировать
        )
    #TODO logging
    #TODO proxy
    #TODO server
    bot = Bot(token=API_TOKEN, parse_mode=PARSE_MODE, session=TG_SERVER)
    logger.debug('Bot is configured')
    return bot


# GET REDIS OBJECT
def _get_redis_obj():
    if REDIS_URL is not None:
        redis = Redis.from_url(REDIS_URL,
                               encoding='utf-8',
                               decode_responses=True)
        logger.debug('Redis is configured')
    else:
        redis = _NoneModule("redis", "REDIS_URL")
        logger.debug("Redis isn't configured")

    return redis


# GET DISPATCHER OBJECT
def _get_dp_obj(bot, redis):
    logger.debug("Dispatcher configurate:")
    if not isinstance(redis, _NoneModule):
        cfg = redis.connection_pool.connection_kwargs
        storage = RedisStorage(host=cfg.get("host", "localhost"),
                               port=cfg.get("port", 6379),
                               db=cfg.get("db", 0),
                               password=cfg.get("password"))
        logger.debug('Used by Redis')
    else:
        storage = MemoryStorage()
        logger.debug('Used by MemoryStorage')
    dp = Dispatcher(storage=storage)
    #TODO отказ от структуры загрузки всех handlerов (?)
    dp.message.middleware(GeneralMiddleware())
    from aiogram.utils.callback_answer import CallbackAnswerMiddleware
    dp.callback_query.middleware(GeneralMiddleware())
    dp.include_routers(podcastHandler.router, admin_panel.router)

    logger.debug("Dispatcher is configured")
    return dp


# GET DATABASE OBJECT
def _get_db_obj():
    if DATABASE_URL is not None:
        db = _SQLAlchemy(DATABASE_URL)
        logger.debug("Datebase loaded")
    else:
        db = _NoneModule("db", "DATABASE_URL")
        logger.debug("Datebase not loaded")

    return db


# GET SCHEDULER OBJECT
def _get_scheduler_obj(redis):
    job_defaults = {"misfire_grace_time": 3600}

    if not isinstance(redis, _NoneModule):
        cfg = redis.connection_pool.connection_kwargs
        jobstores = {
            'default':
            RedisJobStore(host=cfg.get("host", "localhost"),
                          port=cfg.get("port", 6379),
                          db=cfg.get("db", 0),
                          password=cfg.get("password"))
        }
    else:
        jobstores = {"default": MemoryJobStore()}

    scheduler = AsyncIOScheduler(jobstores=jobstores,
                                 job_defaults=job_defaults)

    logger.debug("Scheduler configured")
    return scheduler


if __name__ == MAIN_MODULE_NAME:
    bot = _get_bot_obj()
    redis = _get_redis_obj()
    dp = _get_dp_obj(bot, redis)
    db = _get_db_obj() if DATABASE else None
    scheduler = _get_scheduler_obj(redis)

if __name__ == '__main__':
    from cli import cli
    logger.debug("Calling the cli module")
    cli()
