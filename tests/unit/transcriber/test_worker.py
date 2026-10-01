"""Очередь сервиса расшифровки: без модели, с подставной функцией расшифровки."""

import asyncio
import threading
import time
from pathlib import Path

import pytest
from app.transcriber import worker
from app.transcriber.child import OutOfMemoryError
from app.transcriber.worker import Transcript, handle, requeue_unfinished
from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from shared.transcribe import DONE, INBOX_DIR, JOBS, PROCESSING, Job, Result, result_key


@pytest.fixture
def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def files(tmp_path: Path) -> Path:
    (tmp_path / INBOX_DIR).mkdir()
    return tmp_path


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    monkeypatch.setattr(worker, "RETRY_SECONDS", 0)


def _job(**fields) -> Job:
    """Задание, каким его ставит бот: файл назван по id задания."""
    job = Job(file="", **fields)
    job.file = f"{job.id}.mp3"
    return job


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
    def transcribe(_path: Path) -> Transcript:
        return Transcript(text=text, audio_seconds=600.0, model="small")

    return transcribe


def test_job_and_result_survive_json():
    job = _job(number="767", type_episode="main")
    result = Result(job, text="привет", audio_seconds=600.0, seconds=75.5, model="small")

    assert Job.from_json(job.to_json()) == job
    assert Result.from_json(result.to_json()) == result
    assert _job().id != _job().id


def test_unknown_fields_from_another_version_are_ignored():
    job = _job(number="767")
    raw = job.to_json().replace("{", '{"added_later": 1, ', 1)

    assert Job.from_json(raw) == job
    with pytest.raises(ValueError):
        Job.from_json("[1, 2]")


@pytest.mark.asyncio
async def test_job_is_transcribed_reported_and_cleaned_up(redis, files):
    job = _job(number="767", type_episode="main")
    audio = _audio(files, job)
    raw = await _taken(redis, job)

    await handle(redis, raw, _says("привет"), files)

    result = await _result(redis, job)
    assert (result.text, result.audio_seconds, result.model, result.error) == ("привет", 600.0, "small", None)
    assert result.job == job
    assert await redis.lrange(DONE, 0, -1) == [job.id]
    assert await redis.llen(PROCESSING) == 0
    assert 0 < await redis.ttl(result_key(job.id)) <= 14 * 24 * 3600
    assert not audio.exists()


@pytest.mark.asyncio
async def test_missing_file_is_an_error_for_the_hosts(redis, files):
    job = _job()
    raw = await _taken(redis, job)

    await handle(redis, raw, _says("не должно вызываться"), files)

    assert (await _result(redis, job)).error == worker.MISSING_FILE
    assert await redis.lrange(DONE, 0, -1) == [job.id]


@pytest.mark.asyncio
async def test_failed_transcription_is_reported_not_raised(redis, files):
    job = _job()
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
async def test_known_failure_is_reported_by_its_code(redis, files):
    job = _job()
    _audio(files, job)
    raw = await _taken(redis, job)

    def killed(_path: Path) -> Transcript:
        raise OutOfMemoryError("the transcription process was killed")

    await handle(redis, raw, killed, files)

    assert (await _result(redis, job)).error == "out_of_memory"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["../secret.mp3", "secret.mp3", "", "..", "0123456789ab.mp3/../../x"])
async def test_only_files_named_by_the_bot_are_read(redis, files, name):
    secret = files / "secret.mp3"
    secret.write_bytes(b"not for transcription")
    (files / INBOX_DIR / "secret.mp3").write_bytes(b"not a job either")
    job = Job(file=name)
    raw = await _taken(redis, job)

    await handle(redis, raw, _says("прочитано"), files)

    assert (await _result(redis, job)).error == worker.MISSING_FILE
    assert secret.exists() and (files / INBOX_DIR / "secret.mp3").exists()


@pytest.mark.asyncio
async def test_job_that_waited_too_long_is_closed_without_transcribing(redis, files):
    job = _job(requested_at=time.time() - worker.MAX_AGE_SECONDS - 60)
    audio = _audio(files, job)
    raw = await _taken(redis, job)

    await handle(redis, raw, _says("не должно вызываться"), files)

    assert (await _result(redis, job)).error == worker.EXPIRED
    assert not audio.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '{"number": "767"}'])
async def test_unreadable_job_is_dropped_and_does_not_block_the_queue(redis, files, raw):
    await redis.rpush(PROCESSING, raw)

    assert await handle(redis, raw, _says("не должно вызываться"), files) is None
    assert await redis.llen(PROCESSING) == 0

    await redis.rpush(PROCESSING, raw)
    await requeue_unfinished(redis, files)
    assert (await redis.llen(PROCESSING), await redis.llen(JOBS), await redis.llen(DONE)) == (0, 0, 0)


@pytest.mark.asyncio
async def test_interrupted_job_goes_back_to_the_queue_once(redis, files):
    job = _job()
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
async def test_graceful_stop_returns_the_job_without_a_penalty(redis, files):
    job = _job()
    audio = _audio(files, job)
    await redis.rpush(JOBS, job.to_json())
    started = threading.Event()
    release = threading.Event()

    def slow(_path: Path) -> Transcript:
        started.set()
        release.wait(5)
        return Transcript(text="поздно", audio_seconds=1.0, model="small")

    service = asyncio.create_task(worker.run(redis, slow, files, poll_seconds=1))
    await asyncio.to_thread(started.wait, 5)
    service.cancel()
    with pytest.raises(asyncio.CancelledError):
        await service
    release.set()

    [queued] = await redis.lrange(JOBS, 0, -1)
    assert Job.from_json(queued).attempts == 0
    assert (await redis.llen(PROCESSING), await redis.llen(DONE)) == (0, 0)
    assert audio.exists()


@pytest.mark.asyncio
async def test_redis_hiccup_while_saving_does_not_lose_the_transcript(redis, files, monkeypatch):
    job = _job()
    _audio(files, job)
    raw = await _taken(redis, job)
    store = worker._store
    calls = 0

    async def flaky(*args):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RedisConnectionError("redis is restarting")
        await store(*args)

    monkeypatch.setattr(worker, "_store", flaky)

    await handle(redis, raw, _says("час работы"), files)

    assert calls == 3
    assert (await _result(redis, job)).text == "час работы"


@pytest.mark.asyncio
async def test_service_survives_redis_being_down(redis, files, monkeypatch):
    job = _job()
    _audio(files, job)
    await redis.rpush(JOBS, job.to_json())
    blmove = redis.blmove
    failures = 2

    async def flaky(*args, **kwargs):
        nonlocal failures
        if failures:
            failures -= 1
            raise RedisConnectionError("connection refused")
        return await blmove(*args, **kwargs)

    monkeypatch.setattr(redis, "blmove", flaky)

    service = asyncio.create_task(worker.run(redis, _says("дождались"), files, poll_seconds=1, retry_seconds=0))
    try:
        async with asyncio.timeout(10):
            while not await redis.llen(DONE):
                await asyncio.sleep(0.05)
    finally:
        service.cancel()

    assert (await _result(redis, job)).text == "дождались"


@pytest.mark.asyncio
async def test_service_takes_jobs_one_by_one_in_order(redis, files):
    jobs = [_job(number=str(index)) for index in range(3)]
    lock = threading.Lock()
    overlaps = 0

    def transcribe(path: Path) -> Transcript:
        nonlocal overlaps
        # Вторая расшифровка, начавшаяся до конца первой, не смогла бы взять замок.
        if not lock.acquire(blocking=False):
            overlaps += 1
            return Transcript(text="overlap", audio_seconds=1.0, model="small")
        try:
            time.sleep(0.2)
            return Transcript(text=path.stem, audio_seconds=1.0, model="small")
        finally:
            lock.release()

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
    assert [(await _result(redis, job)).text for job in jobs] == [job.id for job in jobs]
    assert overlaps == 0
