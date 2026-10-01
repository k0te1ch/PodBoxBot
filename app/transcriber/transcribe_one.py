"""Расшифровать один файл и напечатать итог в JSON.

Запускается сервисом как отдельный процесс на каждое задание
(:mod:`child`): модель загружается здесь и уходит из памяти вместе с
процессом. Настройки те же ``WHISPER_*``.
"""

import json
import sys
from pathlib import Path
from typing import Any

from settings import Settings


def transcribe(settings: Settings, path: Path) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    model = WhisperModel(
        settings.WHISPER_MODEL,
        device="cpu",
        compute_type=settings.WHISPER_COMPUTE_TYPE,
        cpu_threads=settings.WHISPER_CPU_THREADS,
        download_root=settings.WHISPER_MODELS_DIR,
    )
    segments, info = model.transcribe(
        str(path),
        language=settings.WHISPER_LANGUAGE or None,
        beam_size=settings.WHISPER_BEAM_SIZE,
        vad_filter=True,
    )
    text = " ".join(segment.text.strip() for segment in segments)
    return {"text": text, "audio_seconds": info.duration, "model": settings.WHISPER_MODEL}


if __name__ == "__main__":
    json.dump(transcribe(Settings(), Path(sys.argv[1])), sys.stdout, ensure_ascii=False)
