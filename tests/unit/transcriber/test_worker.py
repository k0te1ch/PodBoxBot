"""Очередь сервиса расшифровки: без модели, с подставной функцией расшифровки."""

import asyncio
from pathlib import Path

import pytest
from app.transcriber import worker
from app.transcriber.worker import Transcript, handle, requeue_unfinished
from fakeredis import FakeAsyncRedis

from shared.transcribe import DONE, INBOX_DIR, JOBS, PROCESSING, Job, Result, result_key


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def files(tmp_path: Path) -> Path:
    (tmp_path / INBOX_DIR).mkdir()
    return tmp_path


def _audio(files: Path, job: Job) -> Path:
    path = files / INBOX_DIR / job.file
    path.write_bytes(b"mp3")
    return path


async def _taken(redis, job: Job) -> str:
    """Задание в том виде, в каком его берёт сервис: уже в ``processing``."""
    raw = job.to_json()
    await redis.rpush(PROCESSING, raw)
    return raw


async def _result(redis, job: Job) -> Result:
    return Result.from_json(await redis.get(result_key(job.id)))


def _says(text: str):
    def transcribe(path: Path) -> Transcript:
        return Transcript(text=f"{text} ({path.name})", audio_seconds=600.0, model="small")

    return transcribe


def test_job_and_result_survive_json():
    job = Job(file="abc.mp3", number="767", type_episode="main")
    result = Result(job, text="привет", audio_seconds=600.0, seconds=75.5, model="small")

    assert Job.from_json(job.to_json()) == job
    assert Result.from_json(result.to_json()) == result
    assert Job(file="a.mp3").id != Job(file="a.mp3").id


@pytest.mark.asyncio
async def test_job_is_transcribed_reported_and_cleaned_up(redis, files):
    job = Job(file="abc.mp3", number="767", type_episode="main")
    audio = _audio(files, job)
    raw = await _taken(redis, job)

    await handle(redis, raw, _says("привет"), files)

    result = await _result(redis, job)
    assert (result.text, result.audio_seconds, result.model, result.error) == (
        "привет (abc.mp3)",
        600.0,
        "small",
        None,
    )
    assert result.job == job
    assert await redis.lrange(DONE, 0, -1) == [job.id]
    assert await redis.llen(PROCESSING) == 0
    assert 0 < await redis.ttl(result_key(job.id)) <= 14 * 24 * 3600
    assert not audio.exists()


@pytest.mark.asyncio
async def test_missing_file_is_an_error_for_the_hosts(redis, files):
    job = Job(file="gone.mp3")
    raw = await _taken(redis, job)

    await handle(redis, raw, _says("не должно вызываться"), files)

    assert (await _result(redis, job)).error == worker.MISSING_FILE
    assert await redis.lrange(DONE, 0, -1) == [job.id]


@pytest.mark.asyncio
async def test_failed_transcription_is_reported_not_raised(redis, files):
    job = Job(file="abc.mp3")
    audio = _audio(files, job)
    raw = await _taken(redis, job)

    def broken(_path: Path) -> Transcript:
        raise MemoryError("out of memory")

    await handle(redis, raw, broken, files)

    result = await _result(redis, job)
    assert (result.error, result.text) == ("MemoryError", "")
    assert await redis.llen(PROCESSING) == 0
    assert not audio.exists()


@pytest.mark.asyncio
async def test_file_name_cannot_point_outside_the_inbox(redis, files):
    secret = files / "secret.mp3"
    secret.write_bytes(b"not for transcription")
    job = Job(file="../secret.mp3")
    raw = await _taken(redis, job)

    await handle(redis, raw, _says("прочитано"), files)

    assert (await _result(redis, job)).error == worker.MISSING_FILE
    assert secret.exists()


@pytest.mark.asyncio
async def test_interrupted_job_goes_back_to_the_queue_once(redis, files):
    job = Job(file="abc.mp3")
    audio = _audio(files, job)
    await _taken(redis, job)

    await requeue_unfinished(redis, files)

    [queued] = await redis.lrange(JOBS, 0, -1)
    assert Job.from_json(queued).attempts == 1
    assert await redis.llen(PROCESSING) == 0
    assert await redis.llen(DONE) == 0
    assert audio.exists()

    # Сервис снова взял задание и снова не дожил до конца: больше не пробуем.
    await redis.lmove(JOBS, PROCESSING, "LEFT", "RIGHT")
    await requeue_unfinished(redis, files)

    assert await redis.llen(JOBS) == 0
    assert (await _result(redis, job)).error == worker.INTERRUPTED
    assert await redis.lrange(DONE, 0, -1) == [job.id]
    assert not audio.exists()


@pytest.mark.asyncio
async def test_service_takes_jobs_one_by_one_in_order(redis, files):
    jobs = [Job(file=f"{index}.mp3", number=str(index)) for index in range(3)]
    running = 0
    most_at_once = 0

    def transcribe(path: Path) -> Transcript:
        nonlocal running, most_at_once
        running += 1
        most_at_once = max(most_at_once, running)
        running -= 1
        return Transcript(text=path.stem, audio_seconds=1.0, model="small")

    for job in jobs:
        _audio(files, job)
        await redis.rpush(JOBS, job.to_json())

    service = asyncio.create_task(worker.run(redis, transcribe, files, poll_seconds=1))
    try:
        async with asyncio.timeout(10):
            while await redis.llen(DONE) < len(jobs):
                await asyncio.sleep(0.05)
    finally:
        service.cancel()

    assert await redis.lrange(DONE, 0, -1) == [job.id for job in jobs]
    assert [(await _result(redis, job)).text for job in jobs] == ["0", "1", "2"]
    assert most_at_once == 1
