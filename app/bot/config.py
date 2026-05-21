# config.py
# Pydantic-settings based configuration

import json
import sys
from pathlib import Path
from typing import Any

import pytz
from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PODCAST SETTINGS
    TIMEZONE: str = "GMT"
    PODCAST_NAME: str
    PODCAST_CITY: str
    PODCAST_DISTRICT: str
    PODCAST_COUNTRY: str
    SUPPORT_LINK: str
    PODCAST_LINK: str

    # TELEGRAM BOT SETTINGS
    TELEGRAM_API_TOKEN: str
    SKIP_UPDATES: bool = False
    FORWARD_CHAT_ID: str

    TELEGRAM_SERVER_API_ID: str
    TELEGRAM_SERVER_API_HASH: str

    # FTP SETTINGS
    FTP_SERVER: str
    FTP_LOGIN: str
    FTP_PASSWORD: str

    # WP SETTINGS
    WP_URL: str
    WP_LOGIN: str
    WP_PASSWORD: str

    # DEBUG
    DEBUG: bool = False

    # LOGGER
    LOG_LEVEL: str = "INFO"

    # TELEGRAM SERVER
    TG_SERVER: str | None = None
    LOCAL: bool = False
    PARSE_MODE: str | None = None

    # PROXY
    PROXY: str | None = None
    PROXY_AUTH: str | None = None

    # DATABASE
    DATABASE: bool = False
    DATABASE_URL: str | None = None
    REDIS_URL: str | None = None
    REDIS_PASSWORD: str | None = None

    # DIRECTORIES / FILES
    KEYBOARDS_DIR: str | None = None
    HANDLERS_DIR: str | None = None
    MODELS_DIR: str | None = None
    DEVELOPER: int | None = None

    ENABLE_APSCHEDULER: bool = False

    # JSON fields
    ADMINS: list[str] = Field(default_factory=list)
    ADMINS_ID: list[int] = Field(default_factory=list)
    HANDLERS: list[str] = Field(default_factory=list)
    KEYBOARDS: list[str] = Field(default_factory=list)
    LANGUAGES: list[str] = Field(default_factory=list)

    # FILES
    COVER_RZ_NAME: str | None = None
    COVER_PS_NAME: str | None = None
    PODCAST: str | None = None
    WP_COOKIE_FILENAME: str | None = None
    FILES_PATH: str = "files"
    LOGS_PATH: str = "logs"
    LOGS_ZIP_NAME: str = "logs.zip"

    # KAFKA
    KAFKA_SERVER: str = "kafka:9092"
    SCHEMA_REGISTRY_URL: str = "http://schema-registry:8081"

    @field_validator("WP_URL")
    @classmethod
    def strip_wp_url(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator(
        "ADMINS",
        "ADMINS_ID",
        "HANDLERS",
        "KEYBOARDS",
        "LANGUAGES",
        mode="before",
    )
    @classmethod
    def parse_json_list(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return v

    @field_validator("DEVELOPER", mode="before")
    @classmethod
    def parse_developer(cls, v: Any) -> int | None:
        if v is None or (isinstance(v, str) and v.strip().lower() in ("none", "")):
            return None
        return int(v)


# -------------------------------------------------------------------
# Singleton + backward-compatible module-level exports
# -------------------------------------------------------------------

settings = Settings()

# Derived paths
PROJECT_PATH = Path.cwd()
SRC_PATH = Path(__file__).parent

PODCAST_GENRE = 186  # constant

TIMEZONE = pytz.timezone(settings.TIMEZONE)

# Telegram
API_TOKEN = settings.TELEGRAM_API_TOKEN
SKIP_UPDATES = settings.SKIP_UPDATES
FORWARD_CHAT_ID = settings.FORWARD_CHAT_ID
API_ID = settings.TELEGRAM_SERVER_API_ID
API_HASH = settings.TELEGRAM_SERVER_API_HASH

# FTP
FTP_SERVER = settings.FTP_SERVER
FTP_LOGIN = settings.FTP_LOGIN
FTP_PASSWORD = settings.FTP_PASSWORD

# WP
WP_URL = settings.WP_URL
WP_LOGIN = settings.WP_LOGIN
WP_PASSWORD = settings.WP_PASSWORD

# Debug/Logger
DEBUG = settings.DEBUG
LOG_LEVEL = settings.LOG_LEVEL

# Telegram server
TG_SERVER = settings.TG_SERVER
LOCAL = settings.LOCAL
PARSE_MODE = settings.PARSE_MODE

# Proxy
PROXY = settings.PROXY
PROXY_AUTH = settings.PROXY_AUTH

# Database
DATABASE = settings.DATABASE
DATABASE_URL = settings.DATABASE_URL
REDIS_URL = settings.REDIS_URL

# Directories
KEYBOARDS_DIR = settings.KEYBOARDS_DIR
HANDLERS_DIR = settings.HANDLERS_DIR
MODELS_DIR = settings.MODELS_DIR
DEVELOPER = settings.DEVELOPER

ENABLE_APSCHEDULER = settings.ENABLE_APSCHEDULER

ADMINS = settings.ADMINS
ADMINS_ID = settings.ADMINS_ID
HANDLERS = settings.HANDLERS
KEYBOARDS = settings.KEYBOARDS
LANGUAGES = settings.LANGUAGES

# Podcast
PODCAST_NAME = settings.PODCAST_NAME
PODCAST_CITY = settings.PODCAST_CITY
PODCAST_DISTRICT = settings.PODCAST_DISTRICT
PODCAST_COUNTRY = settings.PODCAST_COUNTRY
SUPPORT_LINK = settings.SUPPORT_LINK
PODCAST_LINK = settings.PODCAST_LINK

# Files
COVER_RZ_NAME = settings.COVER_RZ_NAME
COVER_PS_NAME = settings.COVER_PS_NAME
PODCAST = settings.PODCAST
WP_COOKIE_FILENAME = settings.WP_COOKIE_FILENAME
LOGS_ZIP_NAME = settings.LOGS_ZIP_NAME

FILES_PATH: Path = PROJECT_PATH / settings.FILES_PATH
LOGS_PATH: Path = PROJECT_PATH / settings.LOGS_PATH

PODCAST_PATH = FILES_PATH / PODCAST if PODCAST else FILES_PATH / "podcast.mp3"
COVER_RZ_PATH = FILES_PATH / COVER_RZ_NAME if COVER_RZ_NAME else FILES_PATH / "cover.jpg"
COVER_PS_PATH = FILES_PATH / COVER_PS_NAME if COVER_PS_NAME else FILES_PATH / "pscover.jpg"
WP_COOKIE_PATH = FILES_PATH / WP_COOKIE_FILENAME if WP_COOKIE_FILENAME else FILES_PATH / "cookie.pkl"
KEYBOARDS_PATH = SRC_PATH / KEYBOARDS_DIR if KEYBOARDS_DIR else SRC_PATH / "keyboards"


# -------------------------------------------------------------------
# Logger setup
# -------------------------------------------------------------------


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


set_up_logger(LOG_LEVEL, LOGS_PATH)

# Create directories if they don't exist
for path in [FILES_PATH, LOGS_PATH]:
    if not path.exists():
        try:
            path.mkdir(parents=True)
            logger.debug(f"Directory {path} created successfully")
        except OSError as e:
            logger.error(f"Error creating directory {path}: {e}")
