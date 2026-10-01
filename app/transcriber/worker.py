"""Очередь расшифровки: взять задание, расшифровать, отдать итог.

Задания идут строго по одному: цикл один, параллельных расшифровок нет.
Взятое задание переносится в ``transcribe:processing`` и убирается оттуда
вместе с записью итога, одной транзакцией.

Что бывает с заданием, кроме успеха:

* сервис убили посреди работы (на слабой машине это, скорее всего, нехватка
  памяти): после перезапуска задание вернётся в очередь, но только один раз.
  Вторая неудача подряд превращается в ошибку для ведущих, а не в
  бесконечный круг перезапусков;
* сервис остановили штатно (``docker stop``, выкладка): задание возвращается
  в очередь без штрафа;
* задание пролежало в очереди дольше :data:`MAX_AGE_SECONDS` (сервис долго
  не запускали): оно закрывается ошибкой, расшифровывать старый выпуск и
  предлагать по нему правки списка уже поздно;
* задание не читается (другая версия бота, мусор в Redis): оно выбрасывается
  с записью в лог и очередь не держит;
* Redis недоступен: сервис ждёт и пробует снова, а не падает.

Сама расшифровка приходит снаружи функцией ``transcribe(path)``: так очередь
проверяется тестами без модели.
"""

import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from redis.exceptions import RedisError

from shared.transcribe import DONE, INBOX_DIR, JOBS, PROCESSING, RESULT_TTL_SECONDS, Job, Result, result_key

MAX_ATTEMPTS = 2
MAX_AGE_SECONDS = 3 * 24 * 3600
POLL_SECONDS = 30
RETRY_SECONDS = 10
FINISH_ATTEMPTS = 30

INTERRUPTED = "interrupted"
MISSING_FILE = "missing_file"
EXPIRED = "expired"

# Имя файла задания бот собирает из id задания; ничего другого сервис не читает.
_FILE_NAME = re.compile(r"[0-9a-f]{12}\.\w{1,5}")


@dataclass
class Transcript:
    text: str
    audio_seconds: float
    model: str


Transcribe = Callable[[Path], Transcript]


def audio_path(files_dir: Path, job: Job) -> Path | None:
    """Файл задания; ``None``, если имя не похоже на то, что кладёт бот."""
    if not _FILE_NAME.fullmatch(job.file):
        return None
    return files_dir / INBOX_DIR / job.file


def _parse(raw: str | bytes) -> Job | None:
    try:
        return Job.from_json(raw)
    except (ValueError, TypeError) as error:
        logger.error(f"transcribe: unreadable job dropped: {error!r}")
        return None


async def _drop(redis: Any, raw: str | bytes) -> None:
    await redis.lrem(PROCESSING, 1, raw)


async def _store(redis: Any, raw: str | bytes, result: Result) -> None:
    """Итог, сигнал боту и уход задания из работы: одной транзакцией."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(result_key(result.job.id), result.to_json(), ex=RESULT_TTL_SECONDS)
        pipe.rpush(DONE, result.job.id)
        pipe.lrem(PROCESSING, 1, raw)
        await pipe.execute()


async def _finish(redis: Any, raw: str | bytes, result: Result, files_dir: Path) -> None:
    """Записать итог и убрать файл задания. Redis может моргнуть: расшифровку,
    на которую ушёл час, из-за этого не выбрасываем, а пробуем ещё."""
    for attempt in range(1, FINISH_ATTEMPTS + 1):
        try:
            await _store(redis, raw, result)
            break
        except RedisError as error:
            if attempt == FINISH_ATTEMPTS:
                raise
            logger.warning(f"transcribe {result.job.id}: redis is not available, retrying: {error!r}")
            await asyncio.sleep(RETRY_SECONDS)
    path = audio_path(files_dir, result.job)
    if path is not None:
        path.unlink(missing_ok=True)


async def _put_back(redis: Any, raw: str | bytes, job: Job) -> None:
    """Вернуть задание в начало очереди."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.lpush(JOBS, job.to_json())
        pipe.lrem(PROCESSING, 1, raw)
        await pipe.execute()


async def requeue_unfinished(redis: Any, files_dir: Path, max_attempts: int = MAX_ATTEMPTS) -> None:
    """Задания, которые остались в работе после перезапуска сервиса."""
    for raw in await redis.lrange(PROCESSING, 0, -1):
        job = _parse(raw)
        if job is None:
            await _drop(redis, raw)
            continue
        job.attempts += 1
        if job.attempts >= max_attempts:
            logger.error(f"transcribe {job.id}: interrupted {job.attempts} times, giving up on {job.file}")
            await _finish(redis, raw, Result(job, error=INTERRUPTED), files_dir)
            continue
        logger.warning(f"transcribe {job.id}: was interrupted, back to the queue ({job.file})")
        await _put_back(redis, raw, job)


def _refusal(job: Job, path: Path | None, now: float) -> str | None:
    """Почему задание не стоит расшифровывать."""
    if now - job.requested_at > MAX_AGE_SECONDS:
        return EXPIRED
    if path is None or not path.is_file():
        return MISSING_FILE
    return None


async def handle(redis: Any, raw: str | bytes, transcribe: Transcribe, files_dir: Path) -> Result | None:
    """Расшифровать одно задание из ``transcribe:processing`` и записать итог."""
    job = _parse(raw)
    if job is None:
        await _drop(redis, raw)
        return None
    path = audio_path(files_dir, job)
    refusal = _refusal(job, path, time.time())
    started = time.monotonic()
    if refusal is not None:
        logger.error(f"transcribe {job.id}: {refusal} ({job.file})")
        result = Result(job, error=refusal)
    else:
        logger.info(f"transcribe {job.id}: {path.name}")
        try:
            transcript = await asyncio.to_thread(transcribe, path)
        except asyncio.CancelledError:
            # Сервис останавливают: задание не виновато, пусть ждёт следующего запуска.
            logger.warning(f"transcribe {job.id}: stopped, back to the queue")
            await asyncio.shield(_put_back(redis, raw, job))
            raise
        except Exception as error:
            logger.exception(f"transcribe {job.id}: failed: {error!r}")
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


async def run(
    redis: Any,
    transcribe: Transcribe,
    files_dir: Path,
    *,
    poll_seconds: int = POLL_SECONDS,
    retry_seconds: float = RETRY_SECONDS,
) -> None:
    """Бесконечный цикл сервиса. Сбой Redis его не роняет: иначе перезапуск
    контейнера засчитался бы заданию как прерванная попытка."""
    recovered = False
    logger.info("transcriber is waiting for jobs")
    while True:
        try:
            if not recovered:
                await requeue_unfinished(redis, files_dir)
                recovered = True
            raw = await redis.blmove(JOBS, PROCESSING, poll_seconds, "LEFT", "RIGHT")
            if raw is not None:
                await handle(redis, raw, transcribe, files_dir)
        except RedisError as error:
            logger.warning(f"transcriber: redis is not available: {error!r}")
            # Что осталось в работе, разберём заново, когда Redis вернётся.
            recovered = False
            await asyncio.sleep(retry_seconds)
