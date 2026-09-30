# config.py — shared config for microservices (Pydantic-settings)

import sys
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import Field
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
    FTP_RETRY_ATTEMPTS: int = 3
    FTP_RETRY_BACKOFF: float = 5.0

    # WordPress
    WP_URL: str | None = None
    WP_LOGIN: str | None = None
    WP_PASSWORD: str | None = None
    WP_APP_PASSWORD: str | None = None
    WP_UPLOAD_TOPIC: str = "publisher.wordpress.upload"
    WP_RESULT_TOPIC: str = "publisher.wordpress.result"
    WP_COOKIE_PATH: str = "/app/data/cookie.json"
    WP_RETRY_ATTEMPTS: int = 3
    WP_RETRY_BACKOFF: float = 10.0
    WP_VERIFY: bool = True  # проверять черновик через REST после сохранения

    # Boosty
    BOOSTY_BLOG: str | None = None  # slug блога (boosty.to/<slug>)
    BOOSTY_AUTH_FILE: str = "/app/data/boosty_auth.json"  # экспорт токенов из браузера
    BOOSTY_OWNER_ID: int | None = None  # числовой id владельца блога (= container_id для upload)
    BOOSTY_SUBSCRIPTION_LEVEL_ID: str | None = None  # id платного уровня подписки
    BOOSTY_PRICE: int = 10  # цена поста (pay-per-post), ₽
    BOOSTY_COVER_PATH: str = "/app/static/boosty_pscover.png"  # обложка-тизер (том static)
    BOOSTY_ADVERTISER_INFO: str = ""  # маркировка рекламы (обязательное поле, пустое ок)
    # publish — сразу подписчикам; draft — черновиком в редактор блога;
    # scheduled — отложенным постом через BOOSTY_SCHEDULE_DELAY_HOURS часов
    BOOSTY_PUBLISH_MODE: Literal["publish", "draft", "scheduled"] = "publish"
    BOOSTY_SCHEDULE_DELAY_HOURS: float = Field(24.0, gt=0)
    BOOSTY_UPLOAD_TOPIC: str = "publisher.boosty.upload"
    BOOSTY_RESULT_TOPIC: str = "publisher.boosty.result"
    BOOSTY_RETRY_ATTEMPTS: int = 3
    BOOSTY_RETRY_BACKOFF: float = 10.0

    # VK Donut: официальный VK API, пост на стене сообщества только для донов
    VK_ACCESS_TOKEN: str | None = None  # user-токен админа сообщества (scope wall,docs,offline)
    VK_GROUP_ID: int | None = None  # id сообщества без минуса
    VK_API_VERSION: str = "5.199"
    VK_DONUT_PAID_DURATION: int = -1  # -1 — пост навсегда только для донов, иначе дни до открытия
    VK_MEDIA: str = "video"  # как прикрепить mp3: video (mp4 с обложкой, плеер) | doc (файл) | none
    VK_COVER_PATH: str = "/app/static/pscover.jpg"  # кадр для mp4 в режиме video
    VK_UPLOAD_TOPIC: str = "publisher.vk.upload"
    VK_RESULT_TOPIC: str = "publisher.vk.result"
    VK_RETRY_ATTEMPTS: int = 3
    VK_RETRY_BACKOFF: float = 10.0

    # Patreon: публичный API v2 постов не создаёт, работаем как веб-редактор
    PATREON_SESSION_FILE: str = "/app/data/patreon_session.json"  # куки session_id + User-Agent
    PATREON_TIER_IDS: list[str] = Field(
        default_factory=list
    )  # id уровней, которым доступен пост; пусто — всем платным патронам
    PATREON_UPLOAD_TOPIC: str = "publisher.patreon.upload"
    PATREON_RESULT_TOPIC: str = "publisher.patreon.result"
    PATREON_RETRY_ATTEMPTS: int = 3
    PATREON_RETRY_BACKOFF: float = 10.0

    # Sponsr: API нет, работаем как веб-редактор по сессионной куке
    SPONSR_SESSION_FILE: str = "/app/data/sponsr_session.json"  # кука SESS + User-Agent
    SPONSR_PROJECT: str | None = None  # slug проекта (sponsr.ru/<slug>)
    SPONSR_UPLOAD_TOPIC: str = "publisher.sponsr.upload"
    SPONSR_RESULT_TOPIC: str = "publisher.sponsr.result"
    SPONSR_RETRY_ATTEMPTS: int = 3
    SPONSR_RETRY_BACKOFF: float = 10.0

    # Проверка опубликованного поста (WordPress/Boosty): CDN и кеши отдают
    # пост не сразу, поэтому несколько попыток с паузой.
    VERIFY_ATTEMPTS: int = 5
    VERIFY_BACKOFF: float = 10.0

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
        retention="14 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level}::{module}::{function}::{line} | {message}",
        level="TRACE",
        backtrace=True,
        diagnose=True,
    )


set_up_logger(settings.LOG_LEVEL, PROJECT_PATH / settings.LOGS_PATH)
