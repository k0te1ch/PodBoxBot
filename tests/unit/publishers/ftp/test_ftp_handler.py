"""Tests for the FTP publisher handler."""

from unittest.mock import AsyncMock, patch

import pytest
from app.shared.kafka.models.upload_event import UploadEvent
from pydantic import ValidationError


class TestHandleUpload:
    @pytest.fixture
    def mock_producer(self):
        producer = AsyncMock()
        producer.send = AsyncMock()
        return producer

    @pytest.mark.asyncio
    async def test_successful_upload(self, sample_upload_event_dict, mock_producer):
        with patch("app.publishers.FTP.main.upload_to_ftp", new_callable=AsyncMock) as mock_ftp:
            from app.publishers.FTP.main import handle_upload

            await handle_upload(sample_upload_event_dict, mock_producer)

            mock_ftp.assert_called_once()
            assert mock_ftp.call_args.kwargs["file_name"] == "rz-123.mp3"

    @pytest.mark.asyncio
    async def test_failed_upload_sends_failure_event(self, sample_upload_event_dict, mock_producer):
        with patch("app.publishers.FTP.main.upload_to_ftp", new_callable=AsyncMock) as mock_ftp:
            mock_ftp.side_effect = ConnectionError("SFTP connection refused")

            from app.publishers.FTP.main import handle_upload

            await handle_upload(sample_upload_event_dict, mock_producer)

            from app.publishers.FTP.main import _publisher

            attempts = _publisher.retry_attempts
            assert mock_ftp.await_count == attempts
            sent = [call.args[1] for call in mock_producer.send.call_args_list]
            assert [e["status"] for e in sent] == ["retrying"] * (attempts - 1) + ["failure"]
            assert all(e["event_type"] == "result" for e in sent)
            assert sent[0]["metadata"] == {"stage": "upload", "attempt": "1", "attempts": str(attempts)}
            result = sent[-1]
            assert "SFTP connection refused" in result["error"]
            assert result["metadata"]["stage"] == "upload"

    @pytest.mark.asyncio
    async def test_transient_error_is_retried(self, sample_upload_event_dict, mock_producer):
        with patch("app.publishers.FTP.main.upload_to_ftp", new_callable=AsyncMock) as mock_ftp:
            mock_ftp.side_effect = [ConnectionError("reset"), None]

            from app.publishers.FTP.main import handle_upload

            await handle_upload(sample_upload_event_dict, mock_producer)

            assert mock_ftp.await_count == 2
            retry_event = mock_producer.send.call_args_list[0].args[1]
            assert retry_event["status"] == "retrying"
            assert retry_event["progress"] is None
            assert "reset" in retry_event["error"]
            assert all(c.args[1]["status"] != "failure" for c in mock_producer.send.call_args_list)

    @pytest.mark.asyncio
    async def test_invalid_payload_skipped(self, mock_producer):
        from app.publishers.FTP.main import handle_upload

        await handle_upload({"bad": "data"}, mock_producer)
        mock_producer.send.assert_not_called()


class TestRemotePath:
    """Маршрутизация файла по подпапкам в зависимости от type_episode."""

    def test_main_episode_goes_to_root(self):
        from app.publishers.FTP.main import _remote_path

        assert _remote_path("0042_rz_13062026.mp3", "main") == "0042_rz_13062026.mp3"

    def test_none_type_goes_to_root(self):
        from app.publishers.FTP.main import _remote_path

        assert _remote_path("0042_rz_13062026.mp3", None) == "0042_rz_13062026.mp3"

    @pytest.mark.parametrize("type_episode", ["aftershow", "postshow"])
    def test_postshow_goes_to_subdir(self, type_episode):
        from app.publishers.FTP.main import FTP_POSTSHOW_DIR, _remote_path

        result = _remote_path("0042_postshow_13062026.mp3", type_episode)
        assert result == f"{FTP_POSTSHOW_DIR}/0042_postshow_13062026.mp3"


class TestUploadEventModel:
    def test_valid_event(self, sample_upload_event_dict):
        event = UploadEvent(**sample_upload_event_dict)
        assert event.file_name == "rz-123.mp3"
        assert event.event_type == "request"

    def test_invalid_status(self, sample_upload_event_dict):
        sample_upload_event_dict["status"] = "bad_status"
        with pytest.raises(ValidationError):
            UploadEvent(**sample_upload_event_dict)

    def test_valid_statuses(self, sample_upload_event_dict):
        for status in ["pending", "uploading", "success", "failure", None]:
            sample_upload_event_dict["status"] = status
            event = UploadEvent(**sample_upload_event_dict)
            assert event.status == status

    def test_progress_bounds(self, sample_upload_event_dict):
        sample_upload_event_dict["progress"] = 1.1
        with pytest.raises(ValidationError):
            UploadEvent(**sample_upload_event_dict)

        sample_upload_event_dict["progress"] = -0.1
        with pytest.raises(ValidationError):
            UploadEvent(**sample_upload_event_dict)

    def test_model_dump(self, sample_upload_event_dict):
        event = UploadEvent(**sample_upload_event_dict)
        dump = event.model_dump()
        assert isinstance(dump, dict)
        assert dump["path"] == "/app/files/rz-123.mp3"
