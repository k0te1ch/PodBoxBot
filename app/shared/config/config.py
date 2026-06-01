# config.py — shared config for microservices (Pydantic-settings)

import sys
from pathlib import Path

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

# === ENV FILE DISCOVERY ===


def _find_env_file() -> str:
    """Ищет .env рядом с main-скриптом микросервиса."""
    import __main__

    main_path = Path(getattr(__main__, "__file__", ""))
    env_path = main_path.parent / ".env"
    if env_path.exists():
        return str(env_path)
    # Fallback: cwd
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return str(cwd_env)
    return ".env"


class SharedSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Logger
    LOG_LEVEL: str = "INFO"
    FILES_PATH: str = "files"
    LOGS_PATH: str = "logs"
    LOGS_ZIP_NAME: str = "logs.zip"
    TIMEZONE: str = "UTC"
    DEBUG: bool = False

    # Kafka
    KAFKA_SERVER: str = "kafka:9092"
    SCHEMA_REGISTRY_URL: str = "http://schema-registry:8081"
    UPLOAD_TOPIC: str = "publisher.ftp.upload"
    RESULT_TOPIC: str = "publisher.ftp.result"

    # FTP
    FTP_SERVER: str | None = None
    FTP_LOGIN: str | None = None
    FTP_PASSWORD: str | None = None
    FTP_POSTSHOW_DIR: str = "postshow"

    # WordPress
    WP_URL: str | None = None
    WP_LOGIN: str | None = None
    WP_PASSWORD: str | None = None
    WP_APP_PASSWORD: str | None = None
    WP_UPLOAD_TOPIC: str = "publisher.wordpress.upload"
    WP_RESULT_TOPIC: str = "publisher.wordpress.result"
    WP_COOKIE_PATH: str = "/app/data/cookie.pkl"

    # Boosty
    BOOSTY_BLOG: str | None = None  # slug блога (boosty.to/<slug>)
    BOOSTY_AUTH_FILE: str = "/app/data/boosty_auth.json"  # экспорт токенов из браузера
    BOOSTY_OWNER_ID: int | None = None  # числовой id владельца блога (= container_id для upload)
    BOOSTY_SUBSCRIPTION_LEVEL_ID: str | None = None  # id платного уровня подписки
    BOOSTY_PRICE: int = 10  # цена поста (pay-per-post), ₽
    BOOSTY_COVER_PATH: str = "/app/files/boosty_pscover.png"  # обложка-тизер (том files)
    BOOSTY_ADVERTISER_INFO: str = ""  # маркировка рекламы (обязательное поле, пустое ок)
    BOOSTY_UPLOAD_TOPIC: str = "publisher.boosty.upload"
    BOOSTY_RESULT_TOPIC: str = "publisher.boosty.result"

    # Metrics
    PUSHGATEWAY_URL: str = "http://localhost:9091"


# Singleton
settings = SharedSettings()

# === PATHS ===
PROJECT_PATH = Path.cwd()
SRC_PATH = Path(__file__).parent


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


set_up_logger(settings.LOG_LEVEL, PROJECT_PATH / settings.LOGS_PATH)
