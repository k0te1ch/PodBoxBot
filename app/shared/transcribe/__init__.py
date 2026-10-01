"""Очередь расшифровки выпусков: общий язык бота и сервиса ``transcriber``.

Обмен идёт через Redis, без Kafka: это эксперимент, который по умолчанию
выключен, и заводить под него топики и Avro-схемы рано.

* ``transcribe:jobs`` (список): задания, бот кладёт в хвост;
* ``transcribe:processing`` (список): задание, которое сервис взял в работу.
  Он там один, поэтому и задание одно: расшифровка идёт по одной за раз;
* ``transcribe:result:<id>`` (строка, живёт две недели): итог, текст или ошибка;
* ``transcribe:done`` (список): id готовых заданий, их забирает бот.

Сам mp3 лежит в общем каталоге ``files``, в подкаталоге :data:`INBOX_DIR`,
под именем задания: бот кладёт его туда, сервис удаляет после работы.
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass, field

JOBS = "transcribe:jobs"
PROCESSING = "transcribe:processing"
DONE = "transcribe:done"
INBOX_DIR = "transcribe"
RESULT_TTL_SECONDS = 14 * 24 * 3600


def result_key(job_id: str) -> str:
    return f"transcribe:result:{job_id}"


@dataclass
class Job:
    """Что расшифровать: имя файла в ``files/transcribe``."""

    file: str
    number: str | None = None
    type_episode: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    requested_at: float = field(default_factory=time.time)
    attempts: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Job":
        return cls(**json.loads(raw))


@dataclass
class Result:
    job: Job
    text: str = ""
    audio_seconds: float = 0.0
    seconds: float = 0.0
    """Сколько заняла расшифровка."""
    model: str = ""
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Result":
        data = json.loads(raw)
        return cls(**{**data, "job": Job(**data["job"])})
