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

            mock_producer.send.assert_called_once()
            call_args = mock_producer.send.call_args
            result = call_args[0][1]
            assert result["status"] == "failure"
            assert "SFTP connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_payload_skipped(self, mock_producer):
        from app.publishers.FTP.main import handle_upload

        await handle_upload({"bad": "data"}, mock_producer)
        mock_producer.send.assert_not_called()


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
