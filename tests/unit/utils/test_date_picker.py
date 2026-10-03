"""Кнопки выбора даты и времени: быстрые варианты, календарь, слоты."""

from datetime import date, datetime

import pytest

from utils import date_picker
from utils.date_picker import DateCallback

TODAY = date(2026, 10, 3)


def _texts(rows) -> list[list[str]]:
    return [[button.text for button in row] for row in rows]


def _values(rows) -> list[tuple[str, str]]:
    packed = [DateCallback.unpack(button.callback_data) for row in rows for button in row]
    return [(data.a, data.v) for data in packed if data.a != date_picker.NOOP]


def test_recording_offers_today_yesterday_and_the_calendar():
    rows = date_picker.quick_rows(date_picker.RECORDING, TODAY, "ru")

    assert _texts(rows) == [["Сегодня, 3 октября", "Вчера, 2 октября"], ["📅 Другая дата"]]
    assert _values(rows) == [("set", "2026-10-03"), ("set", "2026-10-02"), ("cal", "2026-10")]


def test_publication_defaults_to_as_usual():
    rows = date_picker.quick_rows(date_picker.PUBLISH, TODAY, "ru")

    assert _texts(rows) == [["Как обычно"], ["Сегодня", "Завтра"], ["📅 Другая дата"]]
    assert _values(rows)[:3] == [("set", "default"), ("time", "2026-10-03"), ("time", "2026-10-04")]


def test_recording_calendar_locks_the_future_and_browses_months():
    rows = date_picker.calendar_rows(date_picker.RECORDING, "2026-10", TODAY, "ru")

    assert _texts(rows)[0] == ["‹", "Октябрь 2026", "›"]
    assert _texts(rows)[1] == ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    assert all(len(row) == 7 for row in rows[2:-1])
    values = _values(rows)
    assert values[0] == ("cal", "2026-09") and values[1] == ("cal", "2026-11")
    assert [v for a, v in values if a == "set"] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    assert _texts(rows)[-1] == ["« К быстрому выбору"]


def test_december_leads_to_january():
    rows = date_picker.calendar_rows(date_picker.PUBLISH, "2026-12", TODAY, "ru")

    assert _values(rows)[1] == ("cal", "2027-01")


def test_time_slots_skip_the_hours_that_passed():
    rows = date_picker.time_rows(date_picker.PUBLISH, TODAY, datetime(2026, 10, 3, 18, 0), "ru")
    assert _texts(rows)[0] == ["20:00", "21:00"]

    tomorrow = date_picker.time_rows(date_picker.PUBLISH, date(2026, 10, 4), datetime(2026, 10, 3, 18, 0), "ru")
    assert [text for row in _texts(tomorrow)[:-1] for text in row] == list(date_picker.TIME_SLOTS)
    assert _values(tomorrow)[0] == ("set", "2026-10-04T0900")


@pytest.mark.parametrize(
    ("raw", "parsed"),
    [
        ("2026-10-05T2000", datetime(2026, 10, 5, 20, 0)),
        ("2026-10-05T20:00", datetime(2026, 10, 5, 20, 0)),
        ("05.10.2026 20:00", datetime(2026, 10, 5, 20, 0)),
        ("05.10.2026", None),
        ("soon", None),
    ],
)
def test_datetime_is_read_from_buttons_and_from_typed_text(raw, parsed):
    assert date_picker.parse_datetime(raw) == parsed


def test_dates_read_like_a_person_wrote_them():
    assert date_picker.human_date(date(2026, 10, 3), "ru", today=TODAY) == "3 октября"
    assert date_picker.human_date(date(2025, 12, 31), "ru", today=TODAY) == "31 декабря 2025"
    assert date_picker.human_date(date(2026, 10, 3), "en", today=TODAY) == "October 3"
    assert date_picker.human_datetime(datetime(2026, 10, 5, 9, 5), "ru", today=TODAY) == "5 октября, 09:05"


def test_callback_data_fits_the_telegram_limit():
    rows = date_picker.calendar_rows(date_picker.PUBLISH, "2026-10", TODAY, "ru")
    rows += date_picker.time_rows(date_picker.PUBLISH, TODAY, datetime(2026, 10, 3, 0, 0), "ru")

    assert max(len(button.callback_data.encode()) for row in rows for button in row) <= 64
