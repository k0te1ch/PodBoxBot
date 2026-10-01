"""Расшифровка в отдельном процессе.

Модель живёт в дочернем процессе, который запускается на одно задание и
завершается вместе с ним. Так сервис между выпусками занимает десятки
мегабайт, а не держит в памяти библиотеки и остатки модели. И если
расшифровке не хватило памяти, ядро убивает дочерний процесс, а не сервис:
ведущие получают понятную ошибку сразу, без круга перезапусков контейнера.
"""

import json
import signal
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Убит сигналом KILL: в контейнере с лимитом памяти так выглядит её нехватка.
_KILLED = -int(getattr(signal, "SIGKILL", 9))


class TranscriptionError(RuntimeError):
    """Процесс расшифровки завершился с ошибкой; подробности в логе сервиса.

    ``code`` уходит ведущим как причина: бот переводит её на человеческий язык.
    """

    code = "failed"


class OutOfMemoryError(TranscriptionError):
    """Процесс расшифровки убит системой, почти наверняка из-за памяти."""

    code = "out_of_memory"


class TranscriptionTimeoutError(TranscriptionError):
    """Расшифровка не уложилась в отведённое время."""

    code = "timeout"


class ChildTranscriber:
    """Запускает *command* с путём к файлу и читает итог из его вывода (JSON)."""

    def __init__(self, command: Sequence[str], timeout_seconds: float) -> None:
        self.command = list(command)
        self.timeout_seconds = timeout_seconds
        self._child: subprocess.Popen[str] | None = None

    def __call__(self, path: Path) -> dict[str, Any]:
        child = subprocess.Popen([*self.command, str(path)], stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self._child = child
        try:
            output, _errors = child.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            raise TranscriptionTimeoutError(f"no result in {self.timeout_seconds:.0f}s") from None
        finally:
            self._child = None
        if child.returncode == _KILLED:
            raise OutOfMemoryError("the transcription process was killed")
        if child.returncode != 0:
            raise TranscriptionError(f"the transcription process exited with {child.returncode}")
        return json.loads(output)

    def stop(self) -> None:
        """Прервать идущую расшифровку: сервис останавливают."""
        child = self._child
        if child is not None:
            child.kill()
