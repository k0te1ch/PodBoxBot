"""Очередь расшифровки: взять задание, расшифровать, отдать итог.

Задания идут строго по одному: цикл один, параллельных расшифровок нет.
Взятое задание переносится в ``transcribe:processing`` и убирается оттуда
вместе с записью итога. Если сервис убили посреди работы (на слабой машине
это, скорее всего, нехватка памяти), задание после перезапуска вернётся в
очередь, но только один раз: вторая неудача подряд превращается в ошибку для
ведущих, а не в бесконечный круг перезапусков.

Сама расшифровка приходит снаружи функцией ``transcribe(path)``: так очередь
проверяется тестами без модели.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from shared.transcribe import DONE, INBOX_DIR, JOBS, PROCESSING, RESULT_TTL_SECONDS, Job, Result, result_key

MAX_ATTEMPTS = 2
POLL_SECONDS = 30
INTERRUPTED = "interrupted"
MISSING_FILE = "missing_file"


@dataclass
class Transcript:
    text: str
    audio_seconds: float
    model: str


Transcribe = Callable[[Path], Transcript]


def audio_path(files_dir: Path, job: Job) -> Path:
    """Файл задания. Имя приходит из Redis: берётся только оно, без путей наружу."""
    return files_dir / INBOX_DIR / Path(job.file).name


async def _finish(redis: Any, raw: str | bytes, result: Result, files_dir: Path) -> None:
    """Записать итог, сообщить боту, убрать задание из работы и его файл с диска."""
    await redis.set(result_key(result.job.id), result.to_json(), ex=RESULT_TTL_SECONDS)
    await redis.rpush(DONE, result.job.id)
    await redis.lrem(PROCESSING, 1, raw)
    audio_path(files_dir, result.job).unlink(missing_ok=True)


async def requeue_unfinished(redis: Any, files_dir: Path, max_attempts: int = MAX_ATTEMPTS) -> None:
    """Задания, которые остались в работе после перезапуска сервиса."""
    for raw in await redis.lrange(PROCESSING, 0, -1):
        job = Job.from_json(raw)
        job.attempts += 1
        if job.attempts >= max_attempts:
            logger.error(f"transcribe {job.id}: interrupted {job.attempts} times, giving up on {job.file}")
            await _finish(redis, raw, Result(job, error=INTERRUPTED), files_dir)
            continue
        logger.warning(f"transcribe {job.id}: was interrupted, back to the queue ({job.file})")
        await redis.lpush(JOBS, job.to_json())
        await redis.lrem(PROCESSING, 1, raw)


async def handle(redis: Any, raw: str | bytes, transcribe: Transcribe, files_dir: Path) -> Result:
    """Расшифровать одно задание из ``transcribe:processing`` и записать итог."""
    job = Job.from_json(raw)
    path = audio_path(files_dir, job)
    started = time.monotonic()
    if not path.is_file():
        logger.error(f"transcribe {job.id}: no file {path}")
        result = Result(job, error=MISSING_FILE)
    else:
        logger.info(f"transcribe {job.id}: {path.name}")
        try:
            transcript = await asyncio.to_thread(transcribe, path)
        except Exception as error:
            logger.exception(f"transcribe {job.id}: failed")
            result = Result(job, error=type(error).__name__, seconds=time.monotonic() - started)
        else:
            seconds = time.monotonic() - started
            logger.info(f"transcribe {job.id}: {transcript.audio_seconds:.0f}s of audio in {seconds:.0f}s")
            result = Result(
                job,
                text=transcript.text,
                audio_seconds=transcript.audio_seconds,
                seconds=seconds,
                model=transcript.model,
            )
    await _finish(redis, raw, result, files_dir)
    return result


async def run(redis: Any, transcribe: Transcribe, files_dir: Path, *, poll_seconds: int = POLL_SECONDS) -> None:
    """Бесконечный цикл сервиса."""
    await requeue_unfinished(redis, files_dir)
    logger.info("transcriber is waiting for jobs")
    while True:
        raw = await redis.blmove(JOBS, PROCESSING, poll_seconds, "LEFT", "RIGHT")
        if raw is not None:
            await handle(redis, raw, transcribe, files_dir)
