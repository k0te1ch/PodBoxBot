"""Сервис расшифровки выпусков: faster-whisper на CPU, одна задача за раз.

Запускается отдельно от остального стека (профиль ``transcribe`` в
docker-compose) и по умолчанию не стартует. Бот кладёт задание в Redis, когда
у него включён ``TRANSCRIBE_ENABLED``; сервис читает mp3 из общего каталога
``files`` и возвращает текст. Протокол обмена: :mod:`shared.transcribe`.

Память и скорость задают модель и её настройки:

* ``WHISPER_MODEL``: ``small`` по умолчанию, ``medium`` точнее и вдвое с
  лишним тяжелее;
* ``WHISPER_COMPUTE_TYPE``: ``int8`` для CPU;
* ``WHISPER_CPU_THREADS``: сколько ядер отдать расшифровке;
* ``WHISPER_BEAM_SIZE``: 1 быстрее, 5 чуть точнее.

Модель загружается на время задания и выгружается после: между выпусками
сервис памяти почти не занимает.

``docker stop`` посреди расшифровки задание не теряет и не штрафует: по
SIGTERM оно возвращается в очередь и начнётся заново при следующем запуске.
"""

import asyncio
import contextlib
import gc
import os
import signal
from pathlib import Path
from urllib.parse import quote

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from worker import Transcript, run


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    REDIS_URL: str | None = None
    REDIS_PASSWORD: str | None = None
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    FILES_PATH: str = "files"

    WHISPER_MODEL: str = "small"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_CPU_THREADS: int = 2
    WHISPER_BEAM_SIZE: int = 1
    WHISPER_LANGUAGE: str = "ru"
    WHISPER_MODELS_DIR: str | None = None

    @property
    def redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        password = f":{quote(self.REDIS_PASSWORD, safe='')}@" if self.REDIS_PASSWORD else ""
        return f"redis://{password}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


def transcriber(settings: Settings):
    """Функция расшифровки под эти настройки."""

    def transcribe(path: Path) -> Transcript:
        from faster_whisper import WhisperModel

        model = WhisperModel(
            settings.WHISPER_MODEL,
            device="cpu",
            compute_type=settings.WHISPER_COMPUTE_TYPE,
            cpu_threads=settings.WHISPER_CPU_THREADS,
            download_root=settings.WHISPER_MODELS_DIR,
        )
        try:
            segments, info = model.transcribe(
                str(path),
                language=settings.WHISPER_LANGUAGE or None,
                beam_size=settings.WHISPER_BEAM_SIZE,
                vad_filter=True,
            )
            text = " ".join(segment.text.strip() for segment in segments)
            return Transcript(text=text, audio_seconds=info.duration, model=settings.WHISPER_MODEL)
        finally:
            del model
            gc.collect()

    return transcribe


async def main() -> None:
    settings = Settings()
    redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    logger.info(
        f"transcriber: model {settings.WHISPER_MODEL} ({settings.WHISPER_COMPUTE_TYPE}), "
        f"{settings.WHISPER_CPU_THREADS} threads, beam {settings.WHISPER_BEAM_SIZE}"
    )
    service = asyncio.ensure_future(run(redis, transcriber(settings), Path(settings.FILES_PATH)))
    loop = asyncio.get_running_loop()
    for stop in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(stop, service.cancel)
        except NotImplementedError:
            # Windows: сигналы в цикл не заводятся, штатная остановка там не нужна.
            break
    # Отмена здесь и есть штатная остановка: задание уже вернулось в очередь.
    with contextlib.suppress(asyncio.CancelledError):
        await service
    logger.info("transcriber has stopped")


if __name__ == "__main__":
    asyncio.run(main())
    # Поток с расшифровкой прервать нельзя: задание уже вернулось в очередь,
    # ждать его конца незачем.
    os._exit(0)
