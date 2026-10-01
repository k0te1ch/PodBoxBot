"""Расшифровать один файл и напечатать итог в JSON.

Запускается сервисом как отдельный процесс на каждое задание
(:mod:`child`): модель загружается здесь и уходит из памяти вместе с
процессом. Настройки те же ``WHISPER_*``.

Аудио расшифровывается кусками по ``WHISPER_CHUNK_MINUTES`` минут. Если
отдать faster-whisper часовой выпуск целиком, он держит в памяти всё аудио
и разметку пауз для него разом: на часе это больше 4 ГБ, а кусками память не
зависит от длины выпуска. Цена: слово на стыке кусков может потеряться, для
подсказок по тексту это не важно.
"""

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from settings import Settings

SAMPLE_RATE = 16000


def audio_chunks(path: Path, seconds: float) -> Iterator[Any]:
    """Аудио файла кусками: моно, 16 кГц, float32 от -1 до 1."""
    import av
    import numpy as np

    limit = int(seconds * SAMPLE_RATE)
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    parts: list[Any] = []
    size = 0

    def take() -> Any:
        nonlocal parts, size
        chunk = np.concatenate(parts).astype(np.float32) / 32768.0
        parts, size = [], 0
        return chunk

    with av.open(str(path)) as container:
        for frame in container.decode(audio=0):
            for resampled in resampler.resample(frame):
                samples = resampled.to_ndarray().reshape(-1)
                parts.append(samples)
                size += samples.shape[0]
            if size >= limit:
                yield take()
        for resampled in resampler.resample(None):
            samples = resampled.to_ndarray().reshape(-1)
            parts.append(samples)
            size += samples.shape[0]
    if size:
        yield take()


def transcribe(settings: Settings, path: Path) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    model = WhisperModel(
        settings.WHISPER_MODEL,
        device="cpu",
        compute_type=settings.WHISPER_COMPUTE_TYPE,
        cpu_threads=settings.WHISPER_CPU_THREADS,
        download_root=settings.WHISPER_MODELS_DIR,
    )
    texts: list[str] = []
    audio_seconds = 0.0
    for chunk in audio_chunks(path, settings.WHISPER_CHUNK_MINUTES * 60):
        segments, info = model.transcribe(
            chunk,
            language=settings.WHISPER_LANGUAGE or None,
            beam_size=settings.WHISPER_BEAM_SIZE,
            vad_filter=True,
        )
        texts.extend(segment.text.strip() for segment in segments)
        audio_seconds += info.duration
    return {"text": " ".join(texts), "audio_seconds": audio_seconds, "model": settings.WHISPER_MODEL}


if __name__ == "__main__":
    json.dump(transcribe(Settings(), Path(sys.argv[1])), sys.stdout, ensure_ascii=False)
