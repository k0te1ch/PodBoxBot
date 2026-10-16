"""Разбор расписания сервисных сообщений и очередь задач."""

from datetime import datetime, time

import pytest

from services import scheduled_messages as sm

NOW = datetime(2026, 10, 17, 12, 0)


@pytest.mark.parametrize(
    ("raw", "encoded"),
    [
        ("сейчас", "now"),
        ("Now", "now"),
        ("каждый день 12:00", "daily:12:00"),
        ("ежедневно 9", "daily:09:00"),
        ("каждую неделю пн 12:00", "weekly:mon:12:00"),
        ("каждый вторник 18.30", "weekly:tue:18:30"),
        ("по пятницам 20:00", "weekly:fri:20:00"),
        ("every week sun 10:00", "weekly:sun:10:00"),
        ("20.10.2026 12:00", "once:2026-10-20T12:00"),
    ],
)
def test_parse_schedule(raw, encoded):
    schedule = sm.parse_schedule(raw, now=NOW)

    assert schedule is not None
    assert schedule.encode() == encoded
    assert sm.parse_schedule(encoded, now=NOW) == schedule


@pytest.mark.parametrize(
    "raw", ["", "когда-нибудь", "каждый день 25:00", "каждую неделю xx 12:00", "01.01.2020 12:00"]
)
def test_parse_schedule_rejects_garbage_and_past(raw):
    assert sm.parse_schedule(raw, now=NOW) is None


def test_human_text():
    assert sm.parse_schedule("каждую неделю пн 12:00", now=NOW).human("ru") == "каждую неделю, пн в 12:00"
    assert sm.Schedule("daily", clock=time(9, 5)).human("en") == "every day at 09:05"


def test_jobs_are_added_listed_and_removed():
    schedule = sm.parse_schedule("каждую неделю пн 12:00")
    job_id = sm.add_job("Полезный совет", schedule, "t1")
    try:
        assert [job.id for job in sm.list_jobs()] == [job_id]
        assert sm.remove_job("not-ours") is False
        assert sm.remove_job(job_id) is True
        assert sm.list_jobs() == []
    finally:
        sm.remove_job(job_id)
