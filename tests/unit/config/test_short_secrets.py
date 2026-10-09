"""Короткие секреты: SDK не берёт их точным совпадением, а в чат и в журнал
они всё равно попасть не должны.

Значение короче шести знаков вырезается по имени ключа и по месту (адрес,
пара с логином). В любом другом месте текста оно остаётся: иначе пароль
``1234`` стёр бы из журнала каждое такое число.
"""

from types import SimpleNamespace

import pytest
from sagenza_tgbot_sdk.masking import MIN_SECRET_LENGTH, default_masker, mask_secrets

import config
from config import LOGIN_SETTINGS, SECRET_SETTINGS, register_settings_secrets
from shared.secret_masking import register_named_secrets, short_secret_patterns

# Собраны из частей: значения не похожи на настоящие и не цепляют сканеры секретов.
SHORT = "x" + "7Qz"
LONG = "Sftp)" + "pass-0123"
LOGIN = "podcast"


@pytest.fixture(autouse=True)
def clean_masker():
    """До и после теста маскировщик знает только секреты из настроек."""
    default_masker.clear()
    yield
    default_masker.clear()
    register_settings_secrets(config.settings)


@pytest.fixture
def short_password():
    assert len(SHORT) < MIN_SECRET_LENGTH
    register_named_secrets({"FTP_PASSWORD": SHORT}, logins=[LOGIN])
    return SHORT


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        (f"FTP_PASSWORD {SHORT} rejected", "FTP_PASSWORD *** rejected"),
        (f"ftp_password is '{SHORT}'", "ftp_password is '***'"),
        (f"wrong password ({SHORT})", "wrong password (***)"),
        (f"sent PASS {SHORT}", "sent PASS ***"),
        (f"неверный пароль: {SHORT}.", "неверный пароль: ***."),
        (f"login {LOGIN}/{SHORT} refused", f"login {LOGIN}/*** refused"),
        (f"credentials {LOGIN}:{SHORT}", f"credentials {LOGIN}:***"),
        (f"{LOGIN}:{SHORT}@ftp.example.com is down", f"{LOGIN}:***@ftp.example.com is down"),
    ],
)
def test_short_secret_is_masked_by_key_and_by_place(short_password, text, masked):
    assert mask_secrets(text) == masked


def test_short_secret_in_a_url_is_masked(short_password):
    masked = mask_secrets(f"cannot open ftp://{LOGIN}:{SHORT}@ftp.example.com/podcast")

    assert SHORT not in masked
    assert masked.endswith("@ftp.example.com/podcast")


@pytest.mark.parametrize(
    "text",
    [
        f"episode {SHORT} uploaded",
        f"file 0042_{SHORT}_rz.mp3 not found",
        f"password{SHORT}suffix is not the value",
        f"{LOGIN} uploaded {SHORT}",
    ],
)
def test_short_value_outside_a_secret_place_is_kept(short_password, text):
    assert mask_secrets(text) == text


def test_another_value_after_the_key_is_not_touched_by_the_short_pattern():
    """Шаблон короткого секрета срабатывает только на само значение."""
    patterns = short_secret_patterns("FTP_PASSWORD", SHORT, [LOGIN])
    default_masker.add_patterns(*patterns)

    assert mask_secrets(f"{LOGIN}/other") == f"{LOGIN}/other"


def test_long_secret_is_still_cut_out_everywhere():
    register_named_secrets({"FTP_PASSWORD": LONG})

    assert mask_secrets(f"server said {LONG} is wrong") == "server said *** is wrong"


def test_empty_values_register_nothing():
    register_named_secrets({"FTP_PASSWORD": None, "WP_PASSWORD": "", "VK_ACCESS_TOKEN": "   "}, logins=[None, ""])

    assert mask_secrets("episode 42 uploaded") == "episode 42 uploaded"


def test_bot_settings_register_short_secrets():
    """Настройки бота проходят тот же путь: короткий пароль FTP рядом с логином."""
    source = SimpleNamespace(**dict.fromkeys(SECRET_SETTINGS) | {"FTP_PASSWORD": SHORT, "FTP_LOGIN": LOGIN})
    register_settings_secrets(source)

    assert mask_secrets(f"530 Login incorrect: {LOGIN}/{SHORT}") == f"530 Login incorrect: {LOGIN}/***"
    assert mask_secrets(f"episode {SHORT}") == f"episode {SHORT}"


def test_every_login_setting_exists():
    """Опечатка в LOGIN_SETTINGS не должна молча выключить маскировку по месту."""
    assert set(LOGIN_SETTINGS) <= set(config.Settings.model_fields)
