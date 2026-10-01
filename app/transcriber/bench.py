"""Замер расшифровки на этой машине: сколько времени и памяти уйдёт на файл.

Берёт те же настройки, что и сервис (``WHISPER_*`` из ``.env``), и расшифровывает
один файл. Удобно запускать в контейнере сервиса, чтобы учитывались его лимиты::

    docker compose --profile transcribe run --rm transcriber python bench.py files/episode.mp3

Печатает одну строку JSON: длительность аудио, время расшифровки, скорость
относительно аудио и пик памяти процесса.
"""

import json
import sys
import time
from pathlib import Path

from settings import Settings
from transcribe_one import transcribe


def peak_memory_mb() -> int | None:
    """Пик памяти процесса в мегабайтах; ``None``, где система этого не говорит."""
    try:
        import resource
    except ImportError:
        return None
    # Linux отдаёт килобайты.
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


def measure(path: Path) -> dict[str, object]:
    settings = Settings()
    started = time.perf_counter()
    transcript = transcribe(settings, path)
    seconds = time.perf_counter() - started
    return {
        "model": settings.WHISPER_MODEL,
        "compute_type": settings.WHISPER_COMPUTE_TYPE,
        "cpu_threads": settings.WHISPER_CPU_THREADS,
        "beam_size": settings.WHISPER_BEAM_SIZE,
        "audio_seconds": round(transcript["audio_seconds"]),
        "seconds": round(seconds),
        "speed_x_realtime": round(transcript["audio_seconds"] / seconds, 2),
        "peak_memory_mb": peak_memory_mb(),
        "words": len(transcript["text"].split()),
    }


if __name__ == "__main__":
    sys.stdout.write(json.dumps(measure(Path(sys.argv[1])), ensure_ascii=False) + "\n")
