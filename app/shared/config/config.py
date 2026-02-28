# config.py
# author: k0te1ch
# last update: 08.05.2025
# version: 1.1.0

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import pytz
from dotenv import load_dotenv
from loguru import logger

T = TypeVar("T")

# === ENV LOADING ===


def find_env_file() -> Path:
    """
    Ищет .env рядом с main-скриптом, запускаемым из микросервиса
    """
    import __main__

    main_path = Path(__main__.__file__)
    env_path = main_path.parent / ".env"
    if not env_path.exists():
        raise FileNotFoundError(f".env not found in {main_path.parent}")
    return env_path


def load_env():
    env_file = find_env_file()
    env_path = Path.cwd() / env_file
    path = os.environ["PATH"]
    os.environ.clear()
    os.environ["PATH"] = path
    load_dotenv(dotenv_path=env_path, override=True)


# === PATHS ===

PROJECT_PATH = Path.cwd()
SRC_PATH = Path(__file__).parent


# === ENV PARSING ===
def _cast(value: str, type_: Callable[[str], T]) -> T:
    if type_ == bool:
        return value.lower() in {"true", "1", "yes", "on"}
    return type_(value)


def get(
    key: str,
    type: Callable[[str], T] = str,
    default: Any = None,
    required: bool = False,
) -> T:
    raw = os.getenv(key)
    if raw is None or raw.strip().lower() in {"none", ""}:
        if required:
            raise KeyError(f"Required environment variable '{key}' is missing.")
        return default
    try:
        return _cast(raw, type)
    except Exception:
        return default


# === LOGGING ===


def set_up_logger(level: str = "INFO", logs_path: Path = PROJECT_PATH / "logs"):
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> :: <blue>{module}</blue>::<cyan>{function}</cyan>::<cyan>{line}</cyan> | <level>{message}</level>",
        level=level,
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


load_env()

# === SETTINGS ===

LOG_LEVEL = get("LOG_LEVEL", default="INFO")
FILES_PATH: Path = PROJECT_PATH / get("FILES_PATH", default="files")
LOGS_PATH: Path = PROJECT_PATH / get("LOGS_PATH", default="logs")
LOGS_ZIP_NAME = get("LOGS_ZIP_NAME", default="logs.zip")

TIMEZONE = pytz.timezone(get("TIMEZONE", default="UTC"))
DEBUG = get("DEBUG", type=bool, default=False)

set_up_logger(LOG_LEVEL, LOGS_PATH)
