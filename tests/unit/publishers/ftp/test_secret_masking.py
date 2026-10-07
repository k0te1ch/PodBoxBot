"""Секреты публишеров не попадают в логи и в события для бота.

Общий слой (``shared.config`` и ``BasePublisher``) проверяется здесь, на
FTP-публишере: он самый простой. Токены из файлов авторизации проверяются в
тестах своих площадок.
"""

import io
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.shared.config.config import (
    SECRET_SETTINGS,
    SharedSettings,
    mask_record,
    register_settings_secrets,
    set_up_logger,
    settings,
)
from loguru import logger
from sagenza_tgbot_sdk.masking import default_masker

# Собраны из частей: значения не похожи на настоящие и не цепляют сканеры секретов.
FTP_SECRET = "Sftp)" + "pass-0123"
LOCAL_SECRET = "Qwerty)" + "123-local"


@pytest.fixture
def clean_masker():
    """После теста маскировщик знает только секреты из настроек."""
    yield
    default_masker.clear()
    register_settings_secrets(settings)


@pytest.fixture
def log_output(tmp_path, monkeypatch):
    """Настоящие синки публишера: stdout и файл в ``tmp_path``."""
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


def _fail_with_local(password: str) -> None:
    """Секрет лежит только в локальной переменной кадра."""
    raise RuntimeError("площадка отказала")


def test_every_secret_setting_exists():
    """Опечатка в SECRET_SETTINGS не должна молча выключить маскировку."""
    assert set(SECRET_SETTINGS) <= set(SharedSettings.model_fields)


def test_settings_secrets_are_masked_in_the_log(log_output, clean_masker):
    secrets = {name: f"{name.lower()}-value-{index}" for index, name in enumerate(SECRET_SETTINGS)}
    register_settings_secrets(SimpleNamespace(**secrets))

    for value in secrets.values():
        logger.error(f"площадка ответила: неверные данные ({value})")

    files, stdout = log_output()
    assert files.count("площадка ответила: неверные данные (***)") == len(secrets)
    assert stdout.count("площадка ответила: неверные данные (***)") == len(secrets)
    for value in secrets.values():
        assert value not in files
        assert value not in stdout


def test_frame_locals_stay_out_of_the_log(log_output):
    try:
        _fail_with_local(LOCAL_SECRET)
    except RuntimeError:
        logger.exception("не удалось опубликовать")

    files, stdout = log_output()
    assert "RuntimeError: площадка отказала" in files
    assert "площадка отказала" in stdout
    assert LOCAL_SECRET not in files
    assert LOCAL_SECRET not in stdout


def test_frame_locals_stay_out_even_without_masking(log_output):
    """``diagnose=False`` у синков держит локальные переменные вне журнала и без патчера."""
    logger.configure(patcher=lambda record: None)
    try:
        try:
            _fail_with_local(LOCAL_SECRET)
        except RuntimeError:
            logger.exception("не удалось опубликовать")
        files, stdout = log_output()
    finally:
        logger.configure(patcher=mask_record)

    assert "RuntimeError: площадка отказала" in files
    assert LOCAL_SECRET not in files
    assert LOCAL_SECRET not in stdout


def test_request_url_with_credentials_is_masked(log_output):
    try:
        raise ConnectionError(f"cannot connect to sftp://podcast:{LOCAL_SECRET}@ftp.example.com/upload")
    except ConnectionError as error:
        logger.exception(f"Failed to publish ftp/rz-123.mp3: {error}")

    files, stdout = log_output()
    assert "sftp://***@ftp.example.com/upload" in files
    assert LOCAL_SECRET not in files
    assert LOCAL_SECRET not in stdout


@pytest.mark.asyncio
async def test_error_text_sent_to_the_bot_is_masked(sample_upload_event_dict, clean_masker):
    """Текст ошибки из события бот показывает админам в статусе публикации."""
    register_settings_secrets(SimpleNamespace(**dict.fromkeys(SECRET_SETTINGS) | {"FTP_PASSWORD": FTP_SECRET}))
    producer = AsyncMock()
    with patch("app.publishers.FTP.main.upload_to_ftp", new_callable=AsyncMock) as upload:
        upload.side_effect = PermissionError(f"login failed for podcast with {FTP_SECRET}, token=abc123def456")

        from app.publishers.FTP.main import handle_upload

        await handle_upload(sample_upload_event_dict, producer)

    results = [call.args[1] for call in producer.send.call_args_list if call.args[1]["event_type"] == "result"]
    assert [event["status"] for event in results][-1] == "failure"
    assert len(results) > 1
    for event in results:
        assert "login failed for podcast with ***" in event["error"]
        assert FTP_SECRET not in str(event)
        assert "abc123def456" not in str(event)
