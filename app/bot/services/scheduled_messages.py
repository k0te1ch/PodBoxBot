"""Сервисные сообщения по расписанию: разбор «когда» и задачи планировщика.

Расписание в диалоге пишется текстом и хранится строкой, которую понимает
:func:`parse_schedule` (она же возвращается из ``Schedule.encode``):

* ``now`` — отправить сразу;
* ``once:2026-10-20T12:00`` — один раз в указанное время;
* ``daily:12:00`` — каждый день;
* ``weekly:mon:12:00`` — раз в неделю.

Задачи лежат в jobstore планировщика (Redis, а без него в памяти), поэтому
переживают перезапуск бота, если Redis подключён.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from loguru import logger

from config import FORWARD_CHAT_USERNAME, TIMEZONE
from services.scheduler import scheduler
from utils import date_picker

JOB_PREFIX = "service-message-"
TEXT_PREVIEW = 60

WEEKDAYS = {
    "mon": ("пн", "пон", "понедельник", "понедельникам", "mon", "monday"),
    "tue": ("вт", "вто", "вторник", "вторникам", "tue", "tuesday"),
    "wed": ("ср", "сре", "среда", "средам", "среду", "wed", "wednesday"),
    "thu": ("чт", "чет", "четверг", "четвергам", "thu", "thursday"),
    "fri": ("пт", "пят", "пятница", "пятницам", "пятницу", "fri", "friday"),
    "sat": ("сб", "суб", "суббота", "субботам", "субботу", "sat", "saturday"),
    "sun": ("вс", "вос", "воскресенье", "воскресеньям", "sun", "sunday"),
}
WEEKDAY_BY_NAME = {name: code for code, names in WEEKDAYS.items() for name in names}
WEEKDAY_SHORT_RU = {"mon": "пн", "tue": "вт", "wed": "ср", "thu": "чт", "fri": "пт", "sat": "сб", "sun": "вс"}

_NOW_WORDS = {"сейчас", "now", "сразу"}
_DAILY = re.compile(r"^(?:каждый\s+день|ежедневно|every\s+day|daily)\s+(?P<time>.+)$", re.IGNORECASE)
_WEEKLY = re.compile(
    r"^(?:(?:каждую|каждый|каждое|по|every)\s+(?:неделю\s+|week\s+)?|еженедельно\s+|weekly\s+)(?P<day>[a-zа-яё]+)\s+(?P<time>.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Schedule:
    kind: str  # now | once | daily | weekly
    clock: time | None = None
    at: datetime | None = None
    weekday: str | None = None

    def encode(self) -> str:
        if self.kind == "now":
            return "now"
        if self.kind == "once" and self.at is not None:
            return f"once:{self.at.strftime(date_picker.DATETIME_FORMAT)}"
        if self.kind == "daily" and self.clock is not None:
            return f"daily:{self.clock:%H:%M}"
        if self.kind == "weekly" and self.clock is not None and self.weekday:
            return f"weekly:{self.weekday}:{self.clock:%H:%M}"
        raise ValueError(f"incomplete schedule: {self!r}")

    def human(self, lang: str = "ru") -> str:
        if self.kind == "now":
            return "сейчас" if lang == "ru" else "now"
        if self.kind == "once" and self.at is not None:
            return date_picker.human_datetime(self.at, lang)
        if self.kind == "daily" and self.clock is not None:
            return f"каждый день в {self.clock:%H:%M}" if lang == "ru" else f"every day at {self.clock:%H:%M}"
        if self.kind == "weekly" and self.clock is not None and self.weekday:
            if lang == "ru":
                return f"каждую неделю, {WEEKDAY_SHORT_RU[self.weekday]} в {self.clock:%H:%M}"
            return f"every {self.weekday} at {self.clock:%H:%M}"
        return self.kind

    def trigger(self) -> BaseTrigger:
        if self.kind == "once" and self.at is not None:
            return DateTrigger(run_date=self.at, timezone=TIMEZONE)
        if self.kind == "daily" and self.clock is not None:
            return CronTrigger(hour=self.clock.hour, minute=self.clock.minute, timezone=TIMEZONE)
        if self.kind == "weekly" and self.clock is not None and self.weekday:
            return CronTrigger(
                day_of_week=self.weekday, hour=self.clock.hour, minute=self.clock.minute, timezone=TIMEZONE
            )
        raise ValueError(f"schedule {self.kind!r} has no trigger")


def _now() -> datetime:
    return datetime.now(TIMEZONE).replace(tzinfo=None)


def parse_schedule(raw: str, *, now: datetime | None = None) -> Schedule | None:
    """Текст админа или сохранённая строка → расписание; ``None``, если не поняли или время уже прошло."""
    text = " ".join(str(raw).strip().lower().split())
    if not text:
        return None
    if text in _NOW_WORDS or text == "now":
        return Schedule("now")

    if text.startswith(("once:", "daily:", "weekly:")):
        text = _from_encoded(text)
        if text is None:
            return None

    if match := _DAILY.match(text):
        clock = date_picker.parse_time(match["time"])
        return Schedule("daily", clock=clock) if clock else None

    if match := _WEEKLY.match(text):
        weekday = WEEKDAY_BY_NAME.get(match["day"])
        clock = date_picker.parse_time(match["time"])
        return Schedule("weekly", clock=clock, weekday=weekday) if weekday and clock else None

    parsed = date_picker.parse_datetime(text)
    if parsed is not None and parsed > (now or _now()):
        return Schedule("once", at=parsed)
    return None


def _from_encoded(text: str) -> str | None:
    """``weekly:mon:12:00`` → ``каждую неделю mon 12:00``: дальше разбор общий."""
    kind, _, rest = text.partition(":")
    if kind == "once":
        return rest.replace("t", " ")
    if kind == "daily":
        return f"ежедневно {rest}"
    day, _, clock = rest.partition(":")
    return f"каждую {day} {clock}"


def job_id(unique: str) -> str:
    return f"{JOB_PREFIX}{unique}"


async def send_scheduled(text: str) -> None:
    """Задача планировщика: отправляет текст в чат форварда.

    Импорт бота ленивый: ``main`` тянет роутеры, а они — этот модуль.
    """
    import main

    try:
        await main.bot.send_message(chat_id=FORWARD_CHAT_USERNAME, text=text)
    except Exception as e:
        logger.error(f"scheduled service message to {FORWARD_CHAT_USERNAME} failed: {e!r}")
        return
    logger.info(f"scheduled service message sent to {FORWARD_CHAT_USERNAME}")


def add_job(text: str, schedule: Schedule, unique: str) -> str:
    """Ставит задачу в планировщик; возвращает её id."""
    job = scheduler.add_job(
        send_scheduled,
        trigger=schedule.trigger(),
        args=[text],
        id=job_id(unique),
        name=text[:TEXT_PREVIEW],
        replace_existing=True,
    )
    logger.info(f"scheduled service message {job.id}: {schedule.encode()}")
    return job.id


def next_run(job) -> datetime | None:
    """Ближайший запуск; у задачи, добавленной до старта планировщика, его ещё нет."""
    return getattr(job, "next_run_time", None)


def list_jobs() -> list:
    return sorted(
        (job for job in scheduler.get_jobs() if job.id.startswith(JOB_PREFIX)),
        key=lambda job: (next_run(job) is None, next_run(job).timestamp() if next_run(job) else 0),
    )


def remove_job(job_identifier: str) -> bool:
    if not job_identifier.startswith(JOB_PREFIX) or scheduler.get_job(job_identifier) is None:
        return False
    scheduler.remove_job(job_identifier)
    return True
