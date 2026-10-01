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

Каждое задание расшифровывает отдельный процесс (:mod:`child`,
:mod:`transcribe_one`): между выпусками сервис модель в памяти не держит.

``docker stop`` посреди расшифровки задание не теряет и не штрафует: по
SIGTERM оно возвращается в очередь и начнётся заново при следующем запуске.
"""

import asyncio
import contextlib
import signal
import sys
from pathlib import Path

from child import ChildTranscriber
from loguru import logger
from redis.asyncio import Redis
from settings import Settings
from worker import Transcript, run

HERE = Path(__file__).parent


async def main() -> None:
    settings = Settings()
    redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    logger.info(
        f"transcriber: model {settings.WHISPER_MODEL} ({settings.WHISPER_COMPUTE_TYPE}), "
        f"{settings.WHISPER_CPU_THREADS} threads, beam {settings.WHISPER_BEAM_SIZE}"
    )
    child = ChildTranscriber(
        [sys.executable, str(HERE / "transcribe_one.py")], timeout_seconds=settings.WHISPER_TIMEOUT_HOURS * 3600
    )

    def transcribe(path: Path) -> Transcript:
        return Transcript(**child(path))

    service = asyncio.ensure_future(run(redis, transcribe, Path(settings.FILES_PATH)))

    def stop() -> None:
        service.cancel()
        child.stop()

    loop = asyncio.get_running_loop()
    for stop_signal in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(stop_signal, stop)
        except NotImplementedError:
            # Windows: сигналы в цикл не заводятся, штатная остановка там не нужна.
            break
    # Отмена здесь и есть штатная остановка: задание уже вернулось в очередь.
    with contextlib.suppress(asyncio.CancelledError):
        await service
    logger.info("transcriber has stopped")


if __name__ == "__main__":
    asyncio.run(main())
