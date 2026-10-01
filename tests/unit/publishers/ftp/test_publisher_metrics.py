"""Метрики publisher'а в Pushgateway: ошибки по шагу и классу, последняя публикация."""

from unittest.mock import AsyncMock, patch

import pytest
from app.shared.publishers.base import StepFailedError, error_class
from app.shared.publishers.metrics import PublisherMetrics


def test_error_class_unwraps_the_failed_step():
    try:
        try:
            raise TimeoutError("slow")
        except TimeoutError as cause:
            raise StepFailedError("upload", 3, cause) from cause
    except StepFailedError as error:
        assert error_class(error) == "TimeoutError"
    assert error_class(ValueError("x")) == "ValueError"


def test_session_state_and_expiry():
    metrics = PublisherMetrics("boosty")
    metrics.session(ok=True, expires_at=1_900_000_000)
    metrics.session(ok=False)

    assert metrics._session_ok.get({}) == 0
    assert metrics._session_expires_at.get({}) == 1_900_000_000
    assert metrics._session_refresh.get({"result": "ok"}) == 1
    assert metrics._session_refresh.get({"result": "error"}) == 1


@pytest.mark.asyncio
async def test_failed_step_is_counted_by_stage_and_root_error(sample_upload_event_dict):
    from app.publishers.FTP.main import _publisher

    with (
        patch("app.publishers.FTP.main.upload_to_ftp", new=AsyncMock(side_effect=ConnectionError("refused"))),
        patch.object(_publisher, "retry_sleep", new=AsyncMock()),
        patch.object(_publisher, "producer", new=AsyncMock()),
        patch.object(_publisher.metrics, "push", new=AsyncMock()),
    ):
        await _publisher._handle(sample_upload_event_dict)

    assert _publisher.metrics._error.get({"stage": "upload", "error": "ConnectionError"}) >= 1
    # Длительность только по эпизоду, без логина админа в метках.
    assert _publisher.metrics._duration.get({"target": "rz-123.mp3"})


@pytest.mark.asyncio
async def test_success_sets_last_publication_time(sample_upload_event_dict):
    from app.publishers.FTP.main import _publisher

    with (
        patch("app.publishers.FTP.main.upload_to_ftp", new=AsyncMock()),
        patch.object(_publisher, "producer", new=AsyncMock()),
        patch.object(_publisher.metrics, "push", new=AsyncMock()),
    ):
        await _publisher._handle(sample_upload_event_dict)

    assert _publisher.metrics._last_success.get({}) > 0
