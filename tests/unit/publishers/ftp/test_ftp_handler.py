"""Tests for the FTP publisher handler."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

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
            sent = [
                call.args[1] for call in mock_producer.send.call_args_list if call.args[1]["event_type"] == "result"
            ]
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
            retry_event = next(
                c.args[1] for c in mock_producer.send.call_args_list if c.args[1]["event_type"] == "result"
            )
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


@asynccontextmanager
async def _cm(value):
    yield value


class TestStageAndProgress:
    @pytest.mark.asyncio
    async def test_upload_stage_is_announced_first(self, sample_upload_event_dict):
        producer = AsyncMock()
        with patch("app.publishers.FTP.main.upload_to_ftp", new_callable=AsyncMock):
            from app.publishers.FTP.main import handle_upload

            await handle_upload(sample_upload_event_dict, producer)

        first = producer.send.call_args_list[0].args[1]
        assert first["event_type"] == "progress"
        assert first["status"] == "pending"
        assert first["metadata"] == {"stage": "upload"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("type_episode", ["main", "aftershow"])
    async def test_progress_then_single_success_for_both_episodes(self, tmp_path, type_episode):
        from app.publishers.FTP import main

        path = tmp_path / "0042_rz.mp3"
        path.write_bytes(b"x" * (64 * 1024 * 3 + 10))
        sftp = MagicMock(makedirs=AsyncMock())
        sftp.open = lambda *_a, **_k: _cm(MagicMock(write=AsyncMock()))
        conn = MagicMock(start_sftp_client=lambda: _cm(sftp))
        producer = AsyncMock()

        with (
            patch.object(main.asyncssh, "connect", lambda *_a, **_k: _cm(conn)),
            patch.object(main, "PROGRESS_INTERVAL", 0),
        ):
            await main.upload_to_ftp(
                str(path), path.name, "u", producer, "topic", chat_id="1", message_id="2", type_episode=type_episode
            )

        sent = [c.args[1] for c in producer.send.call_args_list]
        assert [e["event_type"] for e in sent].count("result") == 1
        assert sent[-1]["status"] == "success"
        assert sent[-1]["type_episode"] == type_episode
        progress = [e for e in sent if e["event_type"] == "progress"]
        assert progress
        assert [e["bytes_uploaded"] for e in progress] == sorted(e["bytes_uploaded"] for e in progress)
        assert all(e["bytes_uploaded"] < e["total_bytes"] for e in progress)
