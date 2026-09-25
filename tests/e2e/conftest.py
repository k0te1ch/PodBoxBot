import functools
import os
import re
from pathlib import Path

import pytest
from dotenv import load_dotenv
from tgtest import client as tgtest_client

pytest_plugins = ["tgtest.pytest_plugin"]

E2E_DIR = Path(__file__).parent
FIXTURES_DIR = E2E_DIR / "fixtures"
LOCALES_DIR = E2E_DIR.parents[1] / "app" / "bot" / "locales"

load_dotenv(E2E_DIR / ".env", override=False)

# Бот выбирает язык по language_code, который Telegram берёт из lang_code
# клиента (у Telethon по умолчанию "en"). Подключаемся с языком E2E_LANG,
# чтобы ответы бота совпадали с фрагментами из phrase().
_LANG = os.getenv("E2E_LANG", "ru")
tgtest_client.TelegramClient = functools.partial(tgtest_client.TelegramClient, lang_code=_LANG, system_lang_code=_LANG)


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def bot_username() -> str:
    name = os.getenv("E2E_BOT_USERNAME") or os.getenv("TG_DEFAULT_BOT")
    if not name:
        pytest.skip("E2E_BOT_USERNAME / TG_DEFAULT_BOT not set")
    return name if name.startswith("@") else f"@{name}"


@pytest.fixture(scope="session")
def sample_mp3() -> Path:
    path = FIXTURES_DIR / "sample.mp3"
    if not path.exists():
        pytest.skip(f"place a real MP3 at {path} to run the upload pipeline")
    return path


@pytest.fixture(scope="session")
def episode_template() -> str:
    return (
        "Number: 999\n"
        "Title: e2e test episode\n"
        "Comment: smoke test from tgtest\n"
        "Tags: e2e, smoke, test\n"
        "Chapters: |\n"
        "00:00:00 - intro\n"
    )


@pytest.fixture(scope="session")
def phrase():
    """Устойчивый фрагмент строки бота на языке E2E_LANG (по умолчанию ru).

    Бот отвечает на языке из настроек Telegram-аккаунта, поэтому тексты
    берутся из его же .ftl, а не хардкодятся. Из значения выкидываются
    HTML-теги и {подстановки}, остаётся самый длинный цельный кусок.
    """
    entries = {}
    for line in (LOCALES_DIR / f"{_LANG}.ftl").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition(" = ")
        if sep and key.isidentifier():
            # Как services/context.py: «\n» в однострочном значении — перенос.
            entries[key] = value.strip().replace("\\n", "\n")

    def get(key: str, *, full: bool = False) -> str:
        value = entries[key]
        if full:
            return value
        parts = re.split(r"<[^>]+>|\{[^}]*\}", value)
        return max((p.strip(" ,.!") for p in parts), key=len)

    return get
