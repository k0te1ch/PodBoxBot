"""Постановка выпуска в очередь расшифровки.

Бот не ждёт сервис: он кладёт задание в Redis и идёт дальше. Сам mp3 при
этом связывается в ``files/transcribe/`` под именем задания. Иначе файл не
дожил бы до расшифровки: каталог ``files`` чистится при следующей загрузке
выпуска, а очередь на слабой машине может идти час. Копию после работы
удаляет сервис.
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

import config as bot_config
from shared.transcribe import INBOX_DIR, JOBS, Job


def transcribe_enabled(*_args: Any) -> bool:
    return bool(bot_config.TRANSCRIBE_ENABLED)


def wanted(type_episode: str | None) -> bool:
    """Нужна ли расшифровка выпуску этого типа."""
    if not transcribe_enabled():
        return False
    return bot_config.TRANSCRIBE_EPISODES == "all" or type_episode == "main"


def _place(source: Path, target: Path) -> None:
    """Жёсткая ссылка, а если том так не умеет, копия."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


async def request_transcript(redis: Any, file: Path, number: Any, type_episode: str | None) -> Job | None:
    """Поставить mp3 в очередь расшифровки; ``None``, если она не нужна."""
    if not wanted(type_episode):
        return None
    job = Job(file="", number=str(number) if number not in (None, "") else None, type_episode=type_episode)
    job.file = f"{job.id}{file.suffix or '.mp3'}"
    await asyncio.to_thread(_place, file, file.parent / INBOX_DIR / job.file)
    await redis.rpush(JOBS, job.to_json())
    logger.info(f"transcribe {job.id}: {file.name} is queued")
    return job
