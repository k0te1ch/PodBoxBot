import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

pytest_plugins = ["tgtest.pytest_plugin"]

E2E_DIR = Path(__file__).parent
FIXTURES_DIR = E2E_DIR / "fixtures"

load_dotenv(E2E_DIR / ".env", override=False)


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
        "Chapters:\n"
        "00:00:00 - intro\n"
    )
