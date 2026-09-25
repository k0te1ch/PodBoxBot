"""monitor_file_progress: гонки со скачиванием через локальный Bot API."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from utils.progress_callbacks import monitor_file_progress


@pytest.mark.asyncio
async def test_missing_temp_dir_waits_for_download(tmp_path):
    """Свежий Bot API: temp ещё не создан — это не ошибка, файл появится в music."""
    music = tmp_path / "music"

    async def bot_api_finishes_download():
        await asyncio.sleep(0.1)
        music.mkdir()
        (music / "file_0.mp3").write_bytes(b"x" * 100)

    with patch("utils.progress_callbacks.PODCAST_PATH", tmp_path / "podcast.mp3"):
        download = asyncio.create_task(bot_api_finishes_download())
        ok = await monitor_file_progress(tmp_path / "temp", 100, AsyncMock(), music, poll_interval=0.01)
        await download

    assert ok is True


@pytest.mark.asyncio
async def test_file_already_moved_to_podcast_path(tmp_path):
    """Handler успел перенести файл в PODCAST_PATH раньше, чем монитор его увидел."""
    (tmp_path / "temp").mkdir()
    podcast = tmp_path / "podcast.mp3"
    podcast.write_bytes(b"x" * 100)

    with patch("utils.progress_callbacks.PODCAST_PATH", podcast):
        ok = await monitor_file_progress(tmp_path / "temp", 100, AsyncMock(), tmp_path / "music", poll_interval=0.01)

    assert ok is True
