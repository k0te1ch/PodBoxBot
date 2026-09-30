import os
import re
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sagenza_tgbot_sdk.menus import parse_ftl

pytest_plugins = ["tgtest.pytest_plugin"]

E2E_DIR = Path(__file__).parent
FIXTURES_DIR = E2E_DIR / "fixtures"
LOCALES_DIR = E2E_DIR.parents[1] / "app" / "bot" / "locales"

load_dotenv(E2E_DIR / ".env", override=False)

# Бот выбирает язык по language_code, который Telegram берёт из lang_code
# клиента (у Telethon по умолчанию "en"). tgtest передаёт язык из
# TG_LANG_CODE: подключаемся с языком E2E_LANG, чтобы ответы бота совпадали
# с фрагментами из phrase().
_LANG = os.getenv("E2E_LANG", "ru")
os.environ.setdefault("TG_LANG_CODE", _LANG)
# Без языкового пакета, как у официальных клиентов, Telegram может не менять
# язык аккаунта, который видит бот (docs/troubleshooting.md в tgtest).
os.environ.setdefault("TG_LANG_PACK", "android")


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


@pytest_asyncio.fixture(autouse=True)
async def _bot_speaks_e2e_lang(tester, bot_username):
    """Пропуск, если бот видит аккаунт на другом языке: фразы из .ftl не совпадут."""
    markers = {
        lang: parse_ftl((LOCALES_DIR / f"{lang}.ftl").read_text(encoding="utf-8"))["ask_typeEpisode"]
        .split(",")[-1]
        .strip(" ?")
        for lang in ("ru", "en")
    }
    async with tester.conversation(bot_username) as chat:
        seen = await chat.detect_language(markers)
    if seen != _LANG:
        pytest.skip(f"bot sees the test account as {seen!r}, expected {_LANG!r}; set E2E_LANG={seen}")


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
    HTML-теги и { $подстановки }, остаётся самый длинный цельный кусок.
    """
    # Тот же разбор .ftl, что у FtlTranslator бота (sagenza-tgbot-sdk).
    entries = parse_ftl((LOCALES_DIR / f"{_LANG}.ftl").read_text(encoding="utf-8"))

    def get(key: str, *, full: bool = False) -> str:
        value = entries[key]
        if full:
            return value
        parts = re.split(r"<[^>]+>|\{[^}]*\}", value)
        return max((p.strip(" ,.!") for p in parts), key=len)

    return get
