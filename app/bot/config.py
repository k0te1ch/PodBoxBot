# config.py
# Pydantic-settings based configuration

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import pytz
from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from loguru import Record


# Эмодзи, которые Telegram принимает как реакцию от бота (ReactionTypeEmoji,
# Bot API 10.3). Остальные отклоняются с REACTION_INVALID.
REACTION_EMOJI = frozenset(
    [
        "❤",
        "👍",
        "👎",
        "🔥",
        "\U0001f970",
        "👏",
        "😁",
        "🤔",
        "🤯",
        "😱",
        "🤬",
        "😢",
        "🎉",
        "🤩",
        "🤮",
        "💩",
        "🙏",
        "👌",
        "🕊",
        "🤡",
        "\U0001f971",
        "\U0001f974",
        "😍",
        "🐳",
        "❤\u200d🔥",
        "🌚",
        "🌭",
        "💯",
        "🤣",
        "⚡",
        "🍌",
        "🏆",
        "💔",
        "🤨",
        "😐",
        "🍓",
        "🍾",
        "💋",
        "🖕",
        "😈",
        "😴",
        "😭",
        "🤓",
        "👻",
        "👨\u200d💻",
        "👀",
        "🎃",
        "🙈",
        "😇",
        "😨",
        "🤝",
        "✍",
        "🤗",
        "\U0001fae1",
        "🎅",
        "🎄",
        "☃",
        "💅",
        "🤪",
        "🗿",
        "🆒",
        "💘",
        "🙉",
        "🦄",
        "😘",
        "💊",
        "🙊",
        "😎",
        "👾",
        "🤷\u200d♂",
        "🤷",
        "🤷\u200d♀",
        "😡",
    ]
)
DEFAULT_REACTION = "👍"
VARIATION_SELECTOR = "️"


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
    # Группа или канал, куда бот форвардит анонсы: username (формат
    # @groupname) или числовой id. По id бот достучится только до чата, в
    # котором состоит, иначе Telegram ответит "Bad Request: chat not found".
    # У приватной группы username нет, для неё годится только id.
    FORWARD_CHAT_USERNAME: str

    TELEGRAM_SERVER_API_ID: str
    TELEGRAM_SERVER_API_HASH: str

    # FTP SETTINGS
    FTP_SERVER: str
    FTP_LOGIN: str
    FTP_PASSWORD: str
    # Подпапка для послешоу. Тот же ключ .env, что читает FTP-публишер
    # (app/shared/config) — бот ищет последний эпизод там, куда публишер льёт.
    FTP_POSTSHOW_DIR: str = "postshow"

    # RSS подкаста: новый эпизод → вопрос админам «Выложить?». Пустой адрес
    # выключает слежение; без Redis оно не запускается (см. services/rss.py).
    RSS_FEED_URL: str | None = "https://podbox.ru/feed/podcast/"
    RSS_POLL_INTERVAL: int = 600
    # Сколько неудачных опросов подряд до предупреждения админам.
    RSS_FAILURE_ALERT: int = 6

    # Списки и статусы таблицей: rich-сообщения Telegram (Bot API 10.1+). Если
    # у кого-то из админов старый клиент показывает их плохо, false вернёт
    # обычный текст.
    RICH_MESSAGES: bool = True

    # Тихий ли закреп анонса в чате форварда: True — без уведомления подписчикам.
    FORWARD_PIN_SILENT: bool = False

    # Платные площадки для послешоу. Кнопка площадки появляется в меню, только
    # когда её publisher настроен и есть доступ к аккаунту.
    BOOSTY_ENABLED: bool = False
    VK_ENABLED: bool = False
    PATREON_ENABLED: bool = False
    SPONSR_ENABLED: bool = False

    # Темы и вопросы от слушателей: один список для ведущих. По умолчанию
    # выключено. TOPICS_CHAT — чат, где слушатели пишут (@username или числовой
    # id), пусто — чат форварда. Хештеги через запятую, без «#»; пустая строка
    # выключает сбор этого типа. На принятое сообщение бот ставит реакцию
    # (TOPICS_ACK_REACTION) и пишет автору эфемерно (TOPICS_ACK_EPHEMERAL).
    # TOPICS_ACK_EMOJI: набор эмодзи через пробел или запятую, реакция каждый
    # раз берётся из него случайно. Годятся только реакции Telegram
    # (REACTION_EMOJI ниже): 👍 🫡 👌 🔥 можно, ✅ нельзя, такие молча пропускаются.
    # TOPICS_DAILY_LIMIT: пунктов от автора за последние 24 часа, 0 без лимита.
    TOPICS_ENABLED: bool = False
    TOPICS_CHAT: str | None = None
    TOPICS_HASHTAG: str = "тема"
    TOPICS_QUESTION_HASHTAG: str = "вопрос"
    TOPICS_ACK_REACTION: bool = True
    TOPICS_ACK_EMOJI: str = "👍 🫡 👌 ✅ 🔥"
    TOPICS_ACK_EPHEMERAL: bool = True
    TOPICS_DAILY_LIMIT: int = 3
    TOPICS_MIN_LENGTH: int = 10
    TOPICS_MAX_LENGTH: int = 500
    # Анкета «Предложить тему или вопрос»: ephemeral — в группе, видна только
    # автору (запасной путь — личка); private — сразу в личке бота; off — без
    # анкеты.
    TOPICS_FORM_MODE: Literal["ephemeral", "private", "off"] = "ephemeral"
    # Чат ведущих (@username или числовой id): в нём админы тоже могут смотреть
    # и чистить список. Пусто — только в личке бота.
    TOPICS_HOSTS_CHAT: str | None = None

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
    # Хост/порт для авто-сборки REDIS_URL когда явный URL не задан.
    # Дефолты совпадают с docker-compose; для bare-metal зайти через REDIS_URL.
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # DIRECTORIES / FILES
    HANDLERS_DIR: str | None = None
    MODELS_DIR: str | None = None
    DEVELOPER: int | None = None

    ENABLE_APSCHEDULER: bool = False

    # Порог заполненности диска (%) и период проверки (сек) для host_watch SDK
    DISK_ALERT_PERCENT: float = 85.0
    DISK_CHECK_INTERVAL: int = 3600

    # JSON fields
    ADMINS: list[str] = Field(default_factory=list)
    ADMINS_ID: list[int] = Field(default_factory=list)
    HANDLERS: list[str] = Field(default_factory=list)
    LANGUAGES: list[str] = Field(default_factory=list)
    # Группы заметок ведущих (/note) и хештеги, по которым бот собирает
    # вопросы слушателей в чате FORWARD_CHAT_USERNAME. Без «#», JSON-списком.
    # Заметка без хештега попадает в последнюю группу.
    NOTE_TAGS: list[str] = Field(default_factory=lambda: ["тема", "вопрос", "комментарий"])

    # FILES
    COVER_RZ_NAME: str | None = None
    COVER_PS_NAME: str | None = None
    PODCAST: str | None = None
    FILES_PATH: str = "files"
    LOGS_PATH: str = "logs"
    LOGS_ZIP_NAME: str = "logs.zip"

    # KAFKA
    KAFKA_SERVER: str = "kafka:9092"
    SCHEMA_REGISTRY_URL: str = "http://schema-registry:8081"

    @field_validator("FORWARD_CHAT_USERNAME")
    @classmethod
    def normalize_forward_username(cls, v: str) -> str:
        # Telegram ждёт username в формате @groupname. Допускаем, что в
        # .env его укажут без @ — приводим к каноничному виду. Числовой id
        # чата (-100…) остаётся как есть.
        v = v.strip()
        if v.startswith("@") or v.lstrip("-").isdigit():
            return v
        return f"@{v}"

    @field_validator(
        "ADMINS",
        "ADMINS_ID",
        "HANDLERS",
        "LANGUAGES",
        "NOTE_TAGS",
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


def _hashtags(raw: str) -> list[str]:
    """«тема, topic» → ``["тема", "topic"]``: без «#», в нижнем регистре, без пустых."""
    return [tag for tag in (part.strip().lstrip("#").lower() for part in raw.split(",")) if tag]


def reaction_set(raw: str) -> list[str]:
    """«👍, 🫡 ✅» → ``["👍", "🫡"]``: только реакции Telegram, без повторов.

    Эмодзи вне списка Telegram отклонит (REACTION_INVALID), поэтому оно молча
    выпадает из набора. Пустой набор заменяется на 👍.
    """
    seen: dict[str, None] = {}
    for part in raw.replace(",", " ").split():
        emoji = part.replace(VARIATION_SELECTOR, "")
        if emoji in REACTION_EMOJI:
            seen[emoji] = None
    return list(seen) or [DEFAULT_REACTION]


# Derived paths
PROJECT_PATH = Path.cwd()
SRC_PATH = Path(__file__).parent

PODCAST_GENRE = 186  # constant

TIMEZONE = pytz.timezone(settings.TIMEZONE)

# Telegram
API_TOKEN = settings.TELEGRAM_API_TOKEN
SKIP_UPDATES = settings.SKIP_UPDATES
FORWARD_CHAT_USERNAME = settings.FORWARD_CHAT_USERNAME
FORWARD_PIN_SILENT = settings.FORWARD_PIN_SILENT
RICH_MESSAGES = settings.RICH_MESSAGES
BOOSTY_ENABLED = settings.BOOSTY_ENABLED
VK_ENABLED = settings.VK_ENABLED
PATREON_ENABLED = settings.PATREON_ENABLED
SPONSR_ENABLED = settings.SPONSR_ENABLED
TOPICS_ENABLED = settings.TOPICS_ENABLED
TOPICS_CHAT = (settings.TOPICS_CHAT or "").strip() or FORWARD_CHAT_USERNAME
TOPICS_HASHTAGS = _hashtags(settings.TOPICS_HASHTAG)
TOPICS_QUESTION_HASHTAGS = _hashtags(settings.TOPICS_QUESTION_HASHTAG)
TOPICS_ACK_REACTION = settings.TOPICS_ACK_REACTION
TOPICS_ACK_EMOJI = reaction_set(settings.TOPICS_ACK_EMOJI)
TOPICS_ACK_EPHEMERAL = settings.TOPICS_ACK_EPHEMERAL
TOPICS_DAILY_LIMIT = settings.TOPICS_DAILY_LIMIT
TOPICS_MIN_LENGTH = settings.TOPICS_MIN_LENGTH
TOPICS_MAX_LENGTH = settings.TOPICS_MAX_LENGTH
TOPICS_FORM_MODE = settings.TOPICS_FORM_MODE
TOPICS_HOSTS_CHAT = (settings.TOPICS_HOSTS_CHAT or "").strip() or None
API_ID = settings.TELEGRAM_SERVER_API_ID
API_HASH = settings.TELEGRAM_SERVER_API_HASH

# FTP
FTP_SERVER = settings.FTP_SERVER
FTP_LOGIN = settings.FTP_LOGIN
FTP_PASSWORD = settings.FTP_PASSWORD
FTP_POSTSHOW_DIR = settings.FTP_POSTSHOW_DIR

# RSS
RSS_FEED_URL = settings.RSS_FEED_URL
RSS_POLL_INTERVAL = settings.RSS_POLL_INTERVAL
RSS_FAILURE_ALERT = settings.RSS_FAILURE_ALERT

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

# REDIS_URL: либо явный (для bare-metal), либо собираем из
# REDIS_PASSWORD + REDIS_HOST/PORT/DB с URL-encoding пароля (защищает
# от спецсимволов: @, :, /, #, ?, &, %).
_REDIS_URL = settings.REDIS_URL
if _REDIS_URL is None and settings.REDIS_PASSWORD:
    from urllib.parse import quote

    _REDIS_URL = (
        f"redis://:{quote(settings.REDIS_PASSWORD, safe='')}"
        f"@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
    )
REDIS_URL = _REDIS_URL

# Directories
HANDLERS_DIR = settings.HANDLERS_DIR
MODELS_DIR = settings.MODELS_DIR
DEVELOPER = settings.DEVELOPER

ENABLE_APSCHEDULER = settings.ENABLE_APSCHEDULER
DISK_ALERT_PERCENT = settings.DISK_ALERT_PERCENT
DISK_CHECK_INTERVAL = settings.DISK_CHECK_INTERVAL
KAFKA_SERVER = settings.KAFKA_SERVER
SCHEMA_REGISTRY_URL = settings.SCHEMA_REGISTRY_URL

ADMINS = settings.ADMINS
ADMINS_ID = settings.ADMINS_ID
HANDLERS = settings.HANDLERS
LANGUAGES = settings.LANGUAGES
NOTE_TAGS = [tag.lstrip("#").lower() for tag in settings.NOTE_TAGS]

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
LOGS_ZIP_NAME = settings.LOGS_ZIP_NAME

FILES_PATH: Path = PROJECT_PATH / settings.FILES_PATH
LOGS_PATH: Path = PROJECT_PATH / settings.LOGS_PATH

PODCAST_PATH = FILES_PATH / PODCAST if PODCAST else FILES_PATH / "podcast.mp3"
STATIC_PATH: Path = PROJECT_PATH / "static"


def _cover_path(name: str) -> Path:
    # Обложку можно подменить, положив файл в том files; по умолчанию берётся
    # та, что запечена в образ из static/. Раньше путь вёл только в files, и на
    # свежем томе бот падал на sendAudio (thumbnail не найден).
    override = FILES_PATH / name
    return override if override.is_file() else STATIC_PATH / name


COVER_RZ_PATH = _cover_path(COVER_RZ_NAME or "cover.jpg")
COVER_PS_PATH = _cover_path(COVER_PS_NAME or "pscover.jpg")


# -------------------------------------------------------------------
# Logger setup
# -------------------------------------------------------------------


# Без retention loguru только ротирует: файлы копятся бесконечно и забивают диск.
LOG_RETENTION = "14 days"

STDOUT_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level>::<blue>{module}</blue>"
    "::<cyan>{function}</cyan>::<cyan>{line}</cyan> | <level>{message}</level>"
)
FILE_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level}::{module}::{function}::{line} | {message}"


def with_context(log_format: str) -> Callable[["Record"], str]:
    """Дописывает к строке лога привязанный контекст, если он есть.

    Контекст апдейта (``update_id``, ``user_id``, ``chat_id``) кладёт
    ``LoggingModule`` из sagenza-tgbot-sdk, ``username`` — хендлеры через
    ``logger.bind``. Строки без контекста остаются прежними.
    """

    def render(record: "Record") -> str:
        context = " | {extra}" if record["extra"] else ""
        return f"{log_format}{context}\n{{exception}}"

    return render


def set_up_logger(log_level: str, logs_path: Path):
    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        format=with_context(STDOUT_LOG_FORMAT),
        level=log_level,
        backtrace=True,
        diagnose=True,
    )
    logger.add(
        logs_path / "file_{time:YYYY-MM-DD_HH-mm-ss}.log",
        rotation="5 MB",
        retention=LOG_RETENTION,
        compression="gz",
        format=with_context(FILE_LOG_FORMAT),
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
