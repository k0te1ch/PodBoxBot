import re
from pathlib import Path

import pytest

from config import Settings

FLAGS = ("BOOSTY_ENABLED", "VK_ENABLED", "PATREON_ENABLED", "SPONSR_ENABLED")
ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"


@pytest.mark.parametrize("flag", FLAGS)
def test_paid_platform_buttons_are_off_by_default(flag):
    # A platform button shows up only once its flag is set in .env. That
    # includes Boosty: a deploy without BOOSTY_ENABLED=true hides its button.
    assert Settings.model_fields[flag].default is False


@pytest.mark.parametrize("flag", FLAGS)
def test_every_platform_flag_is_documented_in_env_example(flag):
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert re.search(rf"^{flag}\s*=", text, re.MULTILINE), f"{flag} missing from .env.example"
