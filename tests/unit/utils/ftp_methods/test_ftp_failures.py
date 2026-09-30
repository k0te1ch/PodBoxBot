"""Номер эпизода, когда FTP пуст или отвечает ошибкой."""

import ftplib
from unittest.mock import MagicMock, patch

import pytest

from utils.ftp_methods import FTP_TIMEOUT, EpisodeNumberError, get_last_post_id


def _ftp_tls(ftp: MagicMock) -> MagicMock:
    ftp_tls = MagicMock()
    ftp_tls.return_value.__enter__.return_value = ftp
    return ftp_tls


@pytest.mark.asyncio
@pytest.mark.parametrize("type_episode", ["main", "aftershow"])
async def test_empty_directory_means_first_episode(type_episode):
    ftp = MagicMock()
    ftp.nlst.return_value = ["cover.jpg"]

    with patch("utils.ftp_methods.ftplib.FTP_TLS", _ftp_tls(ftp)):
        assert await get_last_post_id(type_episode, "srv", "user", "pass") == "0"


@pytest.mark.asyncio
async def test_missing_postshow_directory_is_reported():
    ftp = MagicMock()
    ftp.cwd.side_effect = ftplib.error_perm("550 postshow: No such file or directory")

    with (
        patch("utils.ftp_methods.ftplib.FTP_TLS", _ftp_tls(ftp)),
        pytest.raises(EpisodeNumberError, match="550"),
    ):
        await get_last_post_id("aftershow", "srv", "user", "pass")


@pytest.mark.asyncio
async def test_unreachable_server_is_reported():
    ftp_tls = MagicMock(side_effect=TimeoutError("timed out"))

    with (
        patch("utils.ftp_methods.ftplib.FTP_TLS", ftp_tls),
        pytest.raises(EpisodeNumberError, match="timed out"),
    ):
        await get_last_post_id("main", "srv", "user", "pass")


@pytest.mark.asyncio
async def test_connection_has_a_timeout():
    ftp = MagicMock()
    ftp.nlst.return_value = ["1_rz_a.mp3"]
    ftp_tls = _ftp_tls(ftp)

    with patch("utils.ftp_methods.ftplib.FTP_TLS", ftp_tls):
        await get_last_post_id("main", "srv", "user", "pass")

    assert ftp_tls.call_args.kwargs["timeout"] == FTP_TIMEOUT
