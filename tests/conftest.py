import asyncio
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import roots
# ---------------------------------------------------------------------------
# The suite exercises two layers that live under different roots:
#   * the bot (app/bot), which imports its own modules bare: ``config``,
#     ``middlewares``, ``handlers``, ``services``, ``utils``, ...
#   * shared code imported bare as ``shared.*`` (in the Docker image app/bot
#     and app/shared are merged under /app, so ``shared`` is top-level).
#   * the shared/publisher microservices, imported as ``app.shared.*`` /
#     ``app.publishers.*`` / ``app.bot.*`` from the repository root.
# All three roots must be importable for the whole suite to collect.
_REPO_ROOT = Path(__file__).resolve().parent.parent
for _root in (_REPO_ROOT, _REPO_ROOT / "app", _REPO_ROOT / "app" / "bot"):
    _p = str(_root)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Test environment
# ---------------------------------------------------------------------------
# ``config`` builds a pydantic ``Settings`` instance at import time and several
# fields are required. Provide deterministic dummy values so importing the bot
# (directly or transitively) never depends on a real ``.env``. ``setdefault``
# keeps any value already present in the real environment.
_ENV_DEFAULTS = {
    "PODCAST_NAME": "Test Podcast",
    "PODCAST_CITY": "Testville",
    "PODCAST_DISTRICT": "Test District",
    "PODCAST_COUNTRY": "Testland",
    "SUPPORT_LINK": "https://example.com/support",
    "PODCAST_LINK": "https://example.com/podcast",
    "TELEGRAM_API_TOKEN": "0:test-token",
    "FORWARD_CHAT_USERNAME": "@test_group",
    "TELEGRAM_SERVER_API_ID": "12345",
    "TELEGRAM_SERVER_API_HASH": "test-hash",
    "FTP_SERVER": "ftp.example.com",
    "FTP_LOGIN": "ftp-user",
    "FTP_PASSWORD": "ftp-pass",
    "WP_URL": "https://example.com",
    "WP_LOGIN": "wp-user",
    "WP_PASSWORD": "wp-pass",
    "WP_APP_PASSWORD": "wp-app-pass",
    # List/dir settings the bot reads to parametrize tests and load keyboards.
    # Pinned here so the suite behaves identically with or without a local .env.
    "LANGUAGES": '["ru", "en"]',
    "KEYBOARDS": '["podcast_handler", "admin"]',
    "KEYBOARDS_DIR": "keyboards",
    "HANDLERS_DIR": "handlers",
}
for _key, _value in _ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)

import pytest
from loguru import logger


@pytest.fixture(scope="function")
def event_loop():
    """Создаёт новый цикл событий для каждого теста"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Перенаправление логов loguru в caplog
@pytest.fixture(autouse=True, scope="function")
def loguru_caplog(caplog):
    class PropagateHandler(logging.Handler):
        def emit(self, record):
            logging.getLogger(record.name).handle(record)

    logger.remove()  # Убираем все существующие логгеры loguru
    logger.add(PropagateHandler(), format="{message}")
    yield
    logger.remove()
