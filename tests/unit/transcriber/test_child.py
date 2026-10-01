"""Расшифровка в дочернем процессе: итог, ошибки, нехватка памяти, остановка."""

import signal
import sys
import threading
import time
from pathlib import Path

import pytest
from app.transcriber.child import (
    ChildTranscriber,
    OutOfMemoryError,
    TranscriptionError,
    TranscriptionTimeoutError,
)

AUDIO = Path("episode.mp3")


def _python(code: str, timeout: float = 30) -> ChildTranscriber:
    """Дочерний процесс, который вместо модели выполняет *code*; путь к файлу в ``sys.argv[1]``."""
    return ChildTranscriber([sys.executable, "-c", code], timeout_seconds=timeout)


def test_result_is_read_from_the_child_output():
    child = _python(
        "import json, sys; sys.stdout.reconfigure(encoding='utf-8'); "
        "json.dump({'text': 'привет, ' + sys.argv[1], 'audio_seconds': 600.0, 'model': 'small'}, sys.stdout, "
        "ensure_ascii=False)"
    )

    assert child(AUDIO) == {"text": "привет, episode.mp3", "audio_seconds": 600.0, "model": "small"}


def test_failed_child_is_an_error():
    with pytest.raises(TranscriptionError, match="exited with 3") as failure:
        _python("import sys; sys.exit(3)")(AUDIO)

    assert failure.value.code == "failed"


@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="SIGKILL exists only on POSIX")
def test_child_killed_by_the_system_reads_as_out_of_memory():
    with pytest.raises(OutOfMemoryError) as failure:
        _python("import os, signal; os.kill(os.getpid(), signal.SIGKILL)")(AUDIO)

    assert failure.value.code == "out_of_memory"


def test_stuck_child_is_killed_after_the_timeout():
    started = time.monotonic()

    with pytest.raises(TranscriptionTimeoutError) as failure:
        _python("import time; time.sleep(60)", timeout=1)(AUDIO)

    assert failure.value.code == "timeout"

    assert time.monotonic() - started < 20


def test_stop_interrupts_a_running_child():
    child = _python("import time; time.sleep(60)")
    errors: list[BaseException] = []

    def run() -> None:
        try:
            child(AUDIO)
        except RuntimeError as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.monotonic() + 10
    while child._child is None and time.monotonic() < deadline:
        time.sleep(0.05)
    child.stop()
    thread.join(20)

    assert not thread.is_alive()
    assert len(errors) == 1


def test_stop_without_a_running_child_does_nothing():
    _python("pass").stop()
