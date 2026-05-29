"""Tests for Kafka event models."""

import pytest
from app.shared.kafka.models.upload_event import UploadEvent
from app.shared.kafka.models.wordpress_event import WordPressEvent
from pydantic import ValidationError


class TestUploadEvent:
    def test_minimal_valid(self):
        event = UploadEvent(
            event_type="request",
            file_name="test.mp3",
            path="/files/test.mp3",
            username="user",
        )
        assert event.status is None
        assert event.progress is None

    def test_full_valid(self):
        event = UploadEvent(
            event_type="progress",
            file_name="test.mp3",
            path="/files/test.mp3",
            username="user",
            bytes_uploaded=1000,
            total_bytes=5000,
            progress=0.2,
            transfer_speed=500.0,
            status="uploading",
            chat_id="123",
            message_id="456",
        )
        assert event.progress == 0.2
        assert event.status == "uploading"

    def test_empty_file_name_rejected(self):
        with pytest.raises(ValidationError):
            UploadEvent(
                event_type="request",
                file_name="",
                path="/files/",
                username="user",
            )

    def test_negative_bytes_rejected(self):
        with pytest.raises(ValidationError):
            UploadEvent(
                event_type="request",
                file_name="test.mp3",
                path="/files/test.mp3",
                username="user",
                bytes_uploaded=-1,
            )


class TestWordPressEvent:
    def test_minimal_valid(self):
        event = WordPressEvent(
            event_type="request",
            username="user",
            number="100",
            title="Test Title",
            comment="Description",
            slug="rz-100",
        )
        assert event.chapters == []
        assert event.tags == []
        assert event.duration is None

    def test_full_valid(self):
        event = WordPressEvent(
            event_type="result",
            username="admin",
            status="success",
            chat_id="123",
            message_id="456",
            number="200",
            title="200. Episode Title",
            comment="Detailed description",
            chapters=[["00:00", "Start"], ["05:00", "Topic 1"]],
            tags=["tag1", "tag2"],
            slug="rz-200",
            duration=7200,
        )
        assert len(event.chapters) == 2
        assert event.duration == 7200

    def test_roundtrip_model_dump(self):
        original = WordPressEvent(
            event_type="request",
            username="user",
            number="1",
            title="Title",
            comment="Comment",
            chapters=[["00:00", "Intro"]],
            tags=["test"],
            slug="test-1",
            duration=60,
        )
        dump = original.model_dump()
        restored = WordPressEvent(**dump)
        assert original == restored
