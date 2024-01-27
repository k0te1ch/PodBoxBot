import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)


def getEnvBool(env_name: str) -> Optional[bool]:
    env_val = os.getenv(env_name, "").lower()
    if env_val in {"true", "1"}:
        return True
    elif env_val in {"false", "0"}:
        return False
    return None


# TELEGRAM BOT SETTINGS
API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
SKIP_UPDATES = getEnvBool("SKIP_UPDATES")

# FTP SETTINGS
FTP_SERVER = os.getenv("FTP_SERVER")
FTP_LOGIN = os.getenv("FTP_LOGIN")
FTP_PASSWORD = os.getenv("FTP_PASSWORD")

# WP SETTINGS
WP_URL = os.getenv("WP_URL").rstrip("/")
WP_LOGIN = os.getenv("WP_LOGIN")
WP_PASSWORD = os.getenv("WP_PASSWORD")

# LOGGER SETTINGS
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
from loguru import logger
import sys

logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level>::<blue>{module}</blue>::<cyan>{function}</cyan>::<cyan>{line}</cyan> | <level>{message}</level>",
    level=LOG_LEVEL,
    backtrace=True,
    diagnose=True,
)
MODULE_PATH = os.path.dirname(os.path.realpath(__file__))
if not os.path.exists(f"{MODULE_PATH}/logs"):
    os.mkdir(f"{MODULE_PATH}/logs")

logger.add(
    MODULE_PATH + "/logs/file_{time:YYYY-MM-DD_HH-mm-ss}.log",
    rotation="5 MB",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level}::{module}::{function}::{line} | {message}",
    level="TRACE",
    backtrace=True,
    diagnose=True,
)

# default tg_server is official api server
TG_SERVER = os.getenv("TG_SERVER")
LOCAL = getEnvBool("LOCAL")

# default parse_mode is None
PARSE_MODE = os.getenv("PARSE_MODE")

PROXY = os.getenv("PROXY")

PROXY_AUTH = os.getenv("PROXY_AUTH")

DATABASE = getEnvBool("DATABASE")

DATABASE_URL = os.getenv("DATABASE_URL")

REDIS_URL = os.getenv("REDIS_URL")

KEYBOARDS_DIR = os.getenv("KEYBOARDS_DIR")
HANDLERS_DIR = os.getenv("HANDLERS_DIR")
MODELS_DIR = os.getenv("MODELS_DIR")
CONTEXT_FILE = os.getenv("CONTEXT_FILE")

ENABLE_APSCHEDULER = os.getenv("ENABLE_APSCHEDULER")

ADMINS = json.loads(os.getenv("ADMINS"))

HANDLERS = json.loads(os.getenv("HANDLERS"))

KEYBOARDS = json.loads(os.getenv("KEYBOARDS"))

LANGUAGES = json.loads(os.getenv("LANGUAGES"))


# SOURCES
SRC_PATH = os.path.dirname(os.path.realpath(__file__))
COVER_RZ_NAME = os.getenv("COVER_RZ_NAME")
COVER_PS_NAME = os.getenv("COVER_PS_NAME")
PODCAST = os.getenv("PODCAST")
WP_COOKIE_FILENAME = os.getenv("WP_COOKIE_FILENAME")
FILES_PATH = f"{SRC_PATH}/{os.getenv('FILES_PATH')}"
PODCAST_PATH = f"{FILES_PATH}/{PODCAST}"
COVER_RZ_PATH = f"{FILES_PATH}/{COVER_RZ_NAME}"
COVER_PS_PATH = f"{FILES_PATH}/{COVER_PS_NAME}"
WP_COOKIE_PATH = f"{FILES_PATH}/{WP_COOKIE_FILENAME}"
