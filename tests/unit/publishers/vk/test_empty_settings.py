"""Пустые значения выключенных площадок не ломают конфиг остальных publisher'ов.

``.env.example`` содержит ``VK_GROUP_ID = ""``: раньше ``SharedSettings`` падал
на нём с ``int_parsing``, и не стартовал ни один publisher, даже FTP.
"""

from pathlib import Path

import pytest

from shared.config.config import SharedSettings

ENV_EXAMPLE = Path(__file__).resolve().parents[4] / ".env.example"
EMPTY_KEYS = ("VK_ACCESS_TOKEN", "VK_GROUP_ID", "SPONSR_PROJECT", "PATREON_TIER_IDS", "BOOSTY_OWNER_ID")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in EMPTY_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_env_example_loads():
    settings = SharedSettings(_env_file=ENV_EXAMPLE)

    assert settings.VK_GROUP_ID is None
    assert settings.SPONSR_PROJECT is None


def test_empty_values_in_env_file_mean_unset(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'VK_ACCESS_TOKEN = ""\nVK_GROUP_ID = ""\nSPONSR_PROJECT = ""\nPATREON_TIER_IDS=\nBOOSTY_OWNER_ID=\n',
        encoding="utf-8",
    )

    settings = SharedSettings(_env_file=env_file)

    assert settings.VK_ACCESS_TOKEN is None
    assert settings.VK_GROUP_ID is None
    assert settings.SPONSR_PROJECT is None
    assert settings.PATREON_TIER_IDS == []
    assert settings.BOOSTY_OWNER_ID is None


def test_empty_environment_variables_mean_unset(monkeypatch):
    # docker compose передаёт пустые значения из env_file как пустые переменные.
    for key in EMPTY_KEYS:
        monkeypatch.setenv(key, "")

    settings = SharedSettings(_env_file=None)

    assert settings.VK_GROUP_ID is None
    assert settings.PATREON_TIER_IDS == []


def test_real_values_are_still_parsed(monkeypatch):
    monkeypatch.setenv("VK_GROUP_ID", "123")
    monkeypatch.setenv("SPONSR_PROJECT", "podbox")

    settings = SharedSettings(_env_file=None)

    assert settings.VK_GROUP_ID == 123
    assert settings.SPONSR_PROJECT == "podbox"
