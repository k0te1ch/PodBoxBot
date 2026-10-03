"""Выбор даты и времени кнопками: быстрые варианты, календарь, время.

Нужен диалогу загрузки выпуска (:mod:`forms.upload_file`): дата записи и
дата публикации выбираются нажатием, а не набираются в шаблоне. Клавиатуры
здесь только рисуются; что делать с нажатием, решает
:mod:`handlers.podcast_handler`.

Время публикации можно и написать: под слотами стоит кнопка «Другое
время», а разбор набранного живёт в :func:`parse_time`.

Значения в ``callback_data`` и в ответах диалога: дата ``YYYY-MM-DD``, дата
со временем ``YYYY-MM-DDTHH:MM``, обе в часовом поясе бота.
"""

import calendar
import re
from datetime import date, datetime, time, timedelta

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton

from services.i18n import t

RECORDING = "rec"
"""Дата записи: сегодня или раньше, без времени."""
PUBLISH = "pub"
"""Дата публикации: сегодня или позже, со временем."""

SET = "set"
CALENDAR = "cal"
TIME = "time"
HOME = "home"
NOOP = "noop"
TYPE = "type"
"""«Другое время»: бот ждёт время сообщением, день уже выбран."""

DEFAULT = "default"
"""Публикация «как обычно»: дата не задаётся, площадки работают по своим настройкам."""

TIME_SLOTS = ("09:00", "12:00", "15:00", "18:00", "20:00", "21:00")
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M"

# «19:30», «19.30», «19-30», «19 30», «1930», «930» и просто час «19».
_TIME = re.compile(r"(\d{1,2})(?:\s*[:.\-\s]\s*(\d{2})|(\d{2}))?")

Rows = list[list[InlineKeyboardButton]]


class DateCallback(CallbackData, prefix="dp"):
    k: str
    """Что выбираем: :data:`RECORDING` или :data:`PUBLISH`."""
    a: str
    v: str = ""
    """Значение: дата, дата со временем, месяц ``YYYY-MM`` или ``default``.
    Двоеточие в ``callback_data`` разделяет поля, поэтому время идёт как ``HHMM``."""


def _button(text: str, kind: str, action: str, value: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=DateCallback(k=kind, a=action, v=value).pack())


def month_name(month: int, locale: str) -> str:
    return t("months", locale).split()[month - 1]


def month_genitive(month: int, locale: str) -> str:
    return t("months_genitive", locale).split()[month - 1]


def human_date(value: date, locale: str = "ru", *, today: date | None = None) -> str:
    """«3 октября», а для другого года «3 октября 2025»."""
    text = t("date_day_month", locale, day=value.day, month=month_genitive(value.month, locale))
    if today is not None and value.year == today.year:
        return text
    return f"{text} {value.year}"


def human_datetime(value: datetime, locale: str = "ru", *, today: date | None = None) -> str:
    return f"{human_date(value.date(), locale, today=today)}, {value:%H:%M}"


def parse_date(raw: str) -> date | None:
    """Дата из кнопки (ISO) или набранная руками: ``03.10.2026``, ``3/10/2026``."""
    for fmt in (DATE_FORMAT, "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_time(raw: str) -> time | None:
    """Время, набранное руками: ``19:30``, ``19.30``, ``1930``, ``19 30``, ``19``."""
    found = _TIME.fullmatch(raw.strip())
    if found is None:
        return None
    hour, minute = int(found.group(1)), int(found.group(2) or found.group(3) or 0)
    return time(hour, minute) if hour < 24 and minute < 60 else None


def parse_datetime(raw: str) -> datetime | None:
    """Дата со временем из кнопки или набранная руками: ``05.10.2026 20:00``.

    Время после даты пишется так же свободно, как отдельно: ``05.10.2026 1930``.
    """
    text = " ".join(raw.split())
    for fmt in (DATETIME_FORMAT, "%Y-%m-%dT%H%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    day_text, _, time_text = text.partition(" ")
    day, clock = parse_date(day_text), parse_time(time_text)
    return datetime.combine(day, clock) if day and clock else None


def quick_rows(kind: str, today: date, locale: str) -> Rows:
    """Быстрые варианты шага: то, что выбирают почти всегда, и вход в календарь."""
    other = _button(t("date_other", locale), kind, CALENDAR, f"{today:%Y-%m}")
    if kind == RECORDING:
        yesterday = today - timedelta(days=1)
        return [
            [
                _button(t("date_today", locale, date=human_date(today, locale, today=today)), kind, SET, f"{today}"),
                _button(
                    t("date_yesterday", locale, date=human_date(yesterday, locale, today=today)),
                    kind,
                    SET,
                    f"{yesterday}",
                ),
            ],
            [other],
        ]
    tomorrow = today + timedelta(days=1)
    return [
        [_button(t("date_publish_default", locale), kind, SET, DEFAULT)],
        [
            _button(t("date_publish_today", locale), kind, TIME, f"{today}"),
            _button(t("date_publish_tomorrow", locale), kind, TIME, f"{tomorrow}"),
        ],
        [other],
    ]


def _selectable(kind: str, day: date, today: date) -> bool:
    return day <= today if kind == RECORDING else day >= today


def calendar_rows(kind: str, month: str, today: date, locale: str) -> Rows:
    """Месяц сеткой. День, который выбрать нельзя (запись из будущего,
    публикация в прошлом), показан точкой и не нажимается."""
    year, number = (int(part) for part in month.split("-"))
    first = date(year, number, 1)
    previous = (first - timedelta(days=1)).strftime("%Y-%m")
    following = (first + timedelta(days=32)).strftime("%Y-%m")
    rows: Rows = [
        [
            _button("‹", kind, CALENDAR, previous),
            _button(f"{month_name(number, locale)} {year}", kind, NOOP),
            _button("›", kind, CALENDAR, following),
        ],
        [_button(name, kind, NOOP) for name in t("weekdays", locale).split()],
    ]
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, number):
        row = []
        for day in week:
            if day.month != number:
                row.append(_button(" ", kind, NOOP))
            elif not _selectable(kind, day, today):
                row.append(_button("·", kind, NOOP))
            else:
                label = f"[{day.day}]" if day == today else str(day.day)
                row.append(_button(label, kind, SET if kind == RECORDING else TIME, f"{day}"))
        rows.append(row)
    rows.append([_button(t("date_back", locale), kind, HOME)])
    return rows


def time_rows(kind: str, day: date, now: datetime, locale: str) -> Rows:
    """Время публикации в выбранный день; прошедшие часы сегодняшнего дня скрыты."""
    slots = [
        _button(slot, kind, SET, f"{day}T{slot.replace(':', '')}")
        for slot in TIME_SLOTS
        if datetime.strptime(f"{day} {slot}", "%Y-%m-%d %H:%M") > now
    ]
    rows = [slots[index : index + 3] for index in range(0, len(slots), 3)]
    rows.append([_button(t("date_other_time", locale), kind, TYPE, f"{day}")])
    rows.append([_button(t("date_back", locale), kind, HOME)])
    return rows
