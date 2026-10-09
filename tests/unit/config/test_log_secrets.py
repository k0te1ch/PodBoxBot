"""Секреты не попадают ни в файл журнала, ни в stdout.

У ``logger.add`` параметры ``backtrace`` и ``diagnose`` по умолчанию включены,
а ``diagnose=True`` печатает под каждым кадром трейсбека значения локальных
переменных. Тесты ловят возврат этих параметров к умолчаниям и отключение
маскировки записей.
"""

import io
import logging
import sys
from types import SimpleNamespace

import pytest
from loguru import logger
from sagenza_tgbot_sdk.logs import install_log_masking
from sagenza_tgbot_sdk.masking import default_masker

import config
from config import SECRET_SETTINGS, register_settings_secrets, route_stdlib_logging, set_up_logger

# Собраны из частей: значения не похожи на настоящие и не цепляют сканеры секретов.
FOREIGN_BOT_TOKEN = "987654321:" + "AbC-dEf_" * 5
LOCAL_SECRET = "Qwerty)" + "123-local"


@pytest.fixture
def log_output(tmp_path, monkeypatch):
    """Настоящие синки бота: stdout и файл в ``tmp_path``."""
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    set_up_logger("DEBUG", tmp_path)

    def read() -> tuple[str, str]:
        logger.complete()
        logger.remove()
        files = "".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.log"))
        return files, stdout.getvalue()

    yield read
    logger.remove()


@pytest.fixture
def clean_masker():
    """После теста маскировщик знает только секреты из настроек."""
    yield
    default_masker.clear()
    register_settings_secrets(config.settings)


def _fail_with_local(password: str) -> None:
    """Секрет лежит только в локальной переменной кадра."""
    raise RuntimeError("площадка отказала")


def _fail_with_request_url(token: str) -> None:
    raise ConnectionError(f"404, message='Not Found', url='https://api.telegram.org/file/bot{token}/music/file_1.mp3'")


def test_frame_locals_stay_out_of_the_log(log_output):
    try:
        _fail_with_local(LOCAL_SECRET)
    except RuntimeError:
        logger.exception("не удалось опубликовать")

    files, stdout = log_output()
    assert "не удалось опубликовать" in files
    assert "RuntimeError: площадка отказала" in files
    assert "RuntimeError: площадка отказала" in stdout
    assert LOCAL_SECRET not in files
    assert LOCAL_SECRET not in stdout


def test_frame_locals_stay_out_even_without_masking(log_output):
    """``diagnose=False`` у синков держит локальные переменные вне журнала и без патчера SDK."""
    logger.configure(patcher=lambda record: None)
    try:
        try:
            _fail_with_local(LOCAL_SECRET)
        except RuntimeError:
            logger.exception("не удалось опубликовать")
        files, stdout = log_output()
    finally:
        install_log_masking()

    assert "RuntimeError: площадка отказала" in files
    assert "площадка отказала" in stdout
    assert LOCAL_SECRET not in files
    assert LOCAL_SECRET not in stdout


@pytest.mark.parametrize("token", [config.API_TOKEN, FOREIGN_BOT_TOKEN], ids=["own", "foreign"])
def test_telegram_request_url_is_masked(log_output, token):
    try:
        _fail_with_request_url(token)
    except ConnectionError as error:
        logger.exception(f"не удалось скачать файл: {error}")

    files, stdout = log_output()
    assert "/file/bot***/music/file_1.mp3" in files
    assert "/file/bot***/music/file_1.mp3" in stdout
    assert token not in files
    assert token not in stdout


def test_settings_secrets_are_masked(log_output, clean_masker):
    secrets = {name: f"{name.lower()}-value-{index}" for index, name in enumerate(SECRET_SETTINGS)}
    register_settings_secrets(SimpleNamespace(**secrets))

    for value in secrets.values():
        logger.error(f"площадка ответила: неверные данные ({value})")
    logger.bind(payload={"note": f"ключ {secrets['VK_ACCESS_TOKEN']}"}).warning("запрос отклонён")

    files, stdout = log_output()
    assert files.count("площадка ответила: неверные данные (***)") == len(secrets)
    assert stdout.count("площадка ответила: неверные данные (***)") == len(secrets)
    for value in secrets.values():
        assert value not in files
        assert value not in stdout


def test_every_secret_setting_exists():
    """Опечатка в SECRET_SETTINGS не должна молча выключить маскировку."""
    assert set(SECRET_SETTINGS) <= set(config.Settings.model_fields)


def test_credentials_in_urls_are_masked(log_output):
    logger.info("redis: redis://:" + LOCAL_SECRET + "@redis:6379/0")

    files, stdout = log_output()
    assert "redis://***@redis:6379/0" in files
    assert "redis://***@redis:6379/0" in stdout
    assert LOCAL_SECRET not in files
    assert LOCAL_SECRET not in stdout


def test_stdlib_loggers_go_through_masking(log_output):
    """Предупреждения aiogram и asyncio шли в stderr мимо loguru и маскировки."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        route_stdlib_logging()
        url = f"https://api.telegram.org/bot{FOREIGN_BOT_TOKEN}/getUpdates"
        logging.getLogger("aiogram.dispatcher").error("Failed to fetch updates - %s", url)
        logging.getLogger("aiogram.event").info("Update id=1 is handled")
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)

    files, stdout = log_output()
    assert "Failed to fetch updates - https://api.telegram.org/bot***/getUpdates" in files
    assert "Failed to fetch updates - https://api.telegram.org/bot***/getUpdates" in stdout
    assert FOREIGN_BOT_TOKEN not in files
    assert FOREIGN_BOT_TOKEN not in stdout
    assert "Update id=1 is handled" not in files
