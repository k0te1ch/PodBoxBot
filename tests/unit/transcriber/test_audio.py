"""Нарезка аудио на куски для расшифровки.

Нужны PyAV и numpy из зависимостей сервиса: в окружении бота их нет, там тест
пропускается, а в CI его гоняет джоба ``test-transcriber``.
"""

import math
import struct
import sys
import wave
from pathlib import Path

import pytest

pytest.importorskip("av")
np = pytest.importorskip("numpy")

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "app" / "transcriber"))

from transcribe_one import SAMPLE_RATE, audio_chunks


def _tone(path: Path, seconds: float, rate: int = 44100, channels: int = 2) -> Path:
    """Тон 440 Гц в wav: другая частота и стерео, чтобы нарезке было что приводить."""
    frames = bytearray()
    for index in range(int(seconds * rate)):
        sample = int(12000 * math.sin(2 * math.pi * 440 * index / rate))
        frames += struct.pack("<h", sample) * channels
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(bytes(frames))
    return path


def test_audio_is_cut_into_mono_16k_chunks(tmp_path):
    chunks = list(audio_chunks(_tone(tmp_path / "tone.wav", 25), seconds=10))

    assert len(chunks) == 3
    assert all(chunk.dtype == np.float32 and chunk.ndim == 1 for chunk in chunks)
    # Кусок закрывается по кадрам декодера, поэтому он чуть длиннее заданного.
    assert all(10 * SAMPLE_RATE <= len(chunk) < 10.2 * SAMPLE_RATE for chunk in chunks[:2])
    assert sum(len(chunk) for chunk in chunks) == pytest.approx(25 * SAMPLE_RATE, abs=SAMPLE_RATE // 10)
    assert max(float(np.abs(chunk).max()) for chunk in chunks) == pytest.approx(12000 / 32768, abs=0.05)


def test_short_audio_is_one_chunk(tmp_path):
    [chunk] = audio_chunks(_tone(tmp_path / "short.wav", 2, rate=16000, channels=1), seconds=600)

    assert len(chunk) == pytest.approx(2 * SAMPLE_RATE, abs=SAMPLE_RATE // 10)
