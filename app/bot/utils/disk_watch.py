"""Сторож свободного места: пишет админам, когда диск почти заполнен.

Корень контейнера лежит на overlay того же раздела, что и Docker хоста,
поэтому ``disk_usage("/")`` показывает заполненность диска mini-PC.
Повторное предупреждение уходит только после возврата ниже порога,
чтобы не слать одно и то же каждый час.
"""

import asyncio
import shutil
from dataclasses import dataclass

from loguru import logger

from config import ADMINS_ID, DISK_ALERT_PERCENT, DISK_CHECK_INTERVAL
from utils.messaging import broadcast_message_to_users


@dataclass
class DiskState:
    alerted: bool = False


def used_percent(path: str = "/") -> float:
    usage = shutil.disk_usage(path)
    return usage.used / usage.total * 100


def format_alert(percent: float, path: str = "/") -> str:
    free_gb = shutil.disk_usage(path).free / 1024**3
    return (
        f"⚠️ Диск заполнен на {percent:.0f}% (свободно {free_gb:.1f} ГБ).\n"
        "Проверить: <code>docker system df</code>, "
        "<code>du -sh /var/lib/docker/containers/*</code>."
    )


async def check_once(state: DiskState, threshold: float = DISK_ALERT_PERCENT, path: str = "/") -> bool:
    """Проверяет диск; возвращает True, если отправлено предупреждение."""
    percent = used_percent(path)
    if percent < threshold:
        state.alerted = False
        return False
    if state.alerted:
        return False
    logger.warning(f"Disk usage {percent:.1f}% >= {threshold}%")
    await broadcast_message_to_users(format_alert(percent, path), ADMINS_ID)
    state.alerted = True
    return True


async def watch_disk() -> None:
    state = DiskState()
    while True:
        try:
            await check_once(state)
        except OSError as e:
            logger.error(f"disk check failed: {e!r}")
        await asyncio.sleep(DISK_CHECK_INTERVAL)
