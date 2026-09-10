from unittest.mock import MagicMock, patch

import pytest

from utils.FTP_methods import get_last_post_ID

MAIN_FILES = ["755_rz_ep.mp3", "756_rz_ep.mp3", "cover.jpg"]
POSTSHOW_FILES = ["120_postshow_ep.mp3", "121_postshow_ep.mp3", "notes.txt"]


def _ftp_returning(file_list: list[str]) -> MagicMock:
    ftp = MagicMock()
    ftp.nlst.return_value = file_list
    ftp_tls = MagicMock()
    ftp_tls.return_value.__enter__.return_value = ftp
    return ftp_tls, ftp


@pytest.mark.asyncio
async def test_main_episode_reads_the_ftp_root():
    ftp_tls, ftp = _ftp_returning(MAIN_FILES)

    with patch("utils.FTP_methods.ftplib.FTP_TLS", ftp_tls):
        assert await get_last_post_ID("main", "srv", "user", "pass") == "756"

    ftp.cwd.assert_not_called()


@pytest.mark.asyncio
async def test_postshow_episode_uses_the_configured_directory():
    ftp_tls, ftp = _ftp_returning(POSTSHOW_FILES)

    with (
        patch("utils.FTP_methods.ftplib.FTP_TLS", ftp_tls),
        patch("utils.FTP_methods.FTP_POSTSHOW_DIR", "custom-postshow"),
    ):
        assert await get_last_post_ID("aftershow", "srv", "user", "pass") == "121"

    # Раньше здесь было жёсткое "postshow", и при смене FTP_POSTSHOW_DIR бот
    # считал номер эпизода не в том каталоге, куда льёт публишер.
    ftp.cwd.assert_called_once_with("custom-postshow")
