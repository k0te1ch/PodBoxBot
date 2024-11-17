import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
import pytz

# TODO: Add loading of .env from launch arguments


def loadEnv():
    env_file = os.getenv("ENVFILE", ".env")
    if env_file.endswith(".env"):
        env_path = Path.cwd() / env_file
        load_dotenv(dotenv_path=env_path, override=True)


def get_env_bool(env_name: str, default: bool = False) -> bool:
    env_val = os.getenv(env_name)
    if env_val is None or not isinstance(env_val, str) or env_val.lower() not in ["true", "false", "1", "0"]:
        return default

    env_val_lower = env_val.lower()
    if env_val_lower in ["1", "0"]:
        return bool(int(env_val_lower))

    return env_val_lower == "true"


def get_env_str(env_key: str, default: str = None, required: bool = False) -> str | None:
    env_val = os.getenv(env_key, default)
    if env_val is None or (isinstance(env_val, str) and env_val.lower() == "none"):
        if required:
            raise NameError(f'name "{env_key}" is not defined in your env file')
        return None
    return env_val


def set_up_logger(log_level: str, logs_path: Path):
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level>::<blue>{module}</blue>::<cyan>{function}</cyan>::<cyan>{line}</cyan> | <level>{message}</level>",
        level=log_level,
        backtrace=True,
        diagnose=True,
    )

    logger.add(
        logs_path / "file_{time:YYYY-MM-DD_HH-mm-ss}.log",
        rotation="5 MB",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level}::{module}::{function}::{line} | {message}",
        level="TRACE",
        backtrace=True,
        diagnose=True,
    )


loadEnv()

# SOURCES OF PROJECT
PROJECT_PATH = Path.cwd()
SRC_PATH = Path(__file__).parent

# PODCAST SETTINGS
PODCAST_GENRE = 186  # Just constant
TIMEZONE = pytz.timezone(get_env_str("TIMEZONE", default="GMT"))
PODCAST_NAME = get_env_str("PODCAST_NAME", required=True)
PODCAST_CITY = get_env_str("PODCAST_CITY", required=True)
PODCAST_DISTRICT = get_env_str("PODCAST_DISTRICT", required=True)
PODCAST_COUNTRY = get_env_str("PODCAST_COUNTRY", required=True)
SUPPORT_LINK = get_env_str("SUPPORT_LINK", required=True)
PODCAST_LINK = get_env_str("PODCAST_LINK", required=True)

# TELEGRAM BOT SETTINGS
API_TOKEN = get_env_str("TELEGRAM_API_TOKEN", required=True)
SKIP_UPDATES = get_env_bool("SKIP_UPDATES", default=False)
FORWARD_CHAT_ID = get_env_str("FORWARD_CHAT_ID", required=True)

# FTP SETTINGS
FTP_SERVER = get_env_str("FTP_SERVER", required=True)
FTP_LOGIN = get_env_str("FTP_LOGIN", required=True)
FTP_PASSWORD = get_env_str("FTP_PASSWORD", required=True)

# WP SETTINGS
WP_URL = get_env_str("WP_URL", required=True).rstrip("/")
WP_LOGIN = get_env_str("WP_LOGIN", required=True)
WP_PASSWORD = get_env_str("WP_PASSWORD", required=True)

# LOGGER SETTINGS
LOG_LEVEL = get_env_str("LOG_LEVEL", default="INFO")
LOGS_PATH = PROJECT_PATH / "logs"
set_up_logger(LOG_LEVEL, LOGS_PATH)

# default tg_server is official API server
TG_SERVER = get_env_str("TG_SERVER")
LOCAL = get_env_bool("LOCAL", default=False)

# default parse_mode is None
PARSE_MODE = get_env_str("PARSE_MODE")

PROXY = get_env_str("PROXY")
PROXY_AUTH = get_env_str("PROXY_AUTH")

DATABASE = get_env_bool("DATABASE", default=False)
DATABASE_URL = get_env_str("DATABASE_URL")
REDIS_URL = get_env_str("REDIS_URL")

KEYBOARDS_DIR = get_env_str("KEYBOARDS_DIR")
HANDLERS_DIR = get_env_str("HANDLERS_DIR")
MODELS_DIR = get_env_str("MODELS_DIR")
CONTEXT_FILE = get_env_str("CONTEXT_FILE")

ENABLE_APSCHEDULER = get_env_bool("ENABLE_APSCHEDULER", default=False)

ADMINS = json.loads(get_env_str("ADMINS", default="[]"))
HANDLERS = json.loads(get_env_str("HANDLERS", default="[]"))
KEYBOARDS = json.loads(get_env_str("KEYBOARDS", default="[]"))
LANGUAGES = json.loads(get_env_str("LANGUAGES", default="[]"))

# SOURCES
COVER_RZ_NAME = get_env_str("COVER_RZ_NAME")
COVER_PS_NAME = get_env_str("COVER_PS_NAME")
PODCAST = get_env_str("PODCAST")
WP_COOKIE_FILENAME = get_env_str("WP_COOKIE_FILENAME")

FILES_PATH: Path = PROJECT_PATH / get_env_str("FILES_PATH", default="files")
LOGS_PATH: Path = PROJECT_PATH / get_env_str("LOGS_PATH", default="logs")
LOGS_ZIP_NAME = get_env_str("LOGS_ZIP_NAME", default="logs.zip")

PODCAST_PATH = FILES_PATH / PODCAST
COVER_RZ_PATH = FILES_PATH / COVER_RZ_NAME
COVER_PS_PATH = FILES_PATH / COVER_PS_NAME
WP_COOKIE_PATH = FILES_PATH / WP_COOKIE_FILENAME
KEYBOARDS_PATH = SRC_PATH / KEYBOARDS_DIR

# Create directories if they don't exist
for path in [FILES_PATH, LOGS_PATH]:
    if not path.exists():
        try:
            path.mkdir(parents=True)
            logger.debug(f"Directory {path} created successfully")
        except OSError as e:
            logger.error(f"Error creating directory {path}: {e}")
