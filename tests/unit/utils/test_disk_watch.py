from collections import namedtuple
from unittest.mock import AsyncMock, patch

import pytest

from utils import disk_watch

Usage = namedtuple("Usage", "total used free")


def _usage(percent: float) -> Usage:
    return Usage(100 * 1024**3, percent * 1024**3, (100 - percent) * 1024**3)


@pytest.mark.asyncio
async def test_alerts_once_until_usage_drops():
    state = disk_watch.DiskState()
    send = AsyncMock()
    with (
        patch.object(disk_watch, "broadcast_message_to_users", send),
        patch.object(disk_watch.shutil, "disk_usage") as du,
    ):
        du.return_value = _usage(90)
        assert await disk_watch.check_once(state, threshold=85) is True
        assert await disk_watch.check_once(state, threshold=85) is False

        du.return_value = _usage(50)
        assert await disk_watch.check_once(state, threshold=85) is False

        du.return_value = _usage(95)
        assert await disk_watch.check_once(state, threshold=85) is True

    assert send.await_count == 2


@pytest.mark.asyncio
async def test_no_alert_below_threshold():
    send = AsyncMock()
    with (
        patch.object(disk_watch, "broadcast_message_to_users", send),
        patch.object(disk_watch.shutil, "disk_usage", return_value=_usage(40)),
    ):
        assert await disk_watch.check_once(disk_watch.DiskState(), threshold=85) is False
    send.assert_not_awaited()
