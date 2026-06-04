"""Tests for the Kafka/Schema-Registry readiness gates."""

from unittest.mock import patch

import pytest

from app.shared.kafka import wait_for_kafka as wk


class TestWaitForKafka:
    @pytest.mark.asyncio
    async def test_returns_when_ready_immediately(self):
        """Готовая зависимость → возврат без задержек."""
        with patch.object(wk, "_check_kafka", return_value=True) as chk:
            await wk.wait_for_kafka("kafka:9092", timeout=5)
        chk.assert_called_once_with("kafka:9092")

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        """Пара промахов, затем готовность — функция дожидается, не падает."""
        calls = {"n": 0}

        def flaky(_server):
            calls["n"] += 1
            return calls["n"] >= 3

        with (
            patch.object(wk, "_check_kafka", side_effect=flaky),
            patch.object(wk, "_RETRY_INITIAL_DELAY", 0.0),
            patch.object(wk, "_RETRY_MAX_DELAY", 0.0),
        ):
            await wk.wait_for_kafka("kafka:9092", timeout=5)
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        """Зависимость не поднялась в бюджет → RuntimeError (вызывающий перезапустит)."""
        with (
            patch.object(wk, "_check_kafka", return_value=False),
            patch.object(wk, "_RETRY_INITIAL_DELAY", 0.0),
            patch.object(wk, "_RETRY_MAX_DELAY", 0.0),
            pytest.raises(RuntimeError),
        ):
            await wk.wait_for_kafka("kafka:9092", timeout=0.05)

    @pytest.mark.asyncio
    async def test_stack_waits_for_both(self):
        """Stack-хелпер ждёт и брокер, и schema registry."""
        with (
            patch.object(wk, "_check_kafka", return_value=True) as ck,
            patch.object(wk, "_check_schema_registry", return_value=True) as cs,
        ):
            await wk.wait_for_kafka_stack("kafka:9092", "http://sr:8081", timeout=5)
        ck.assert_called_once()
        cs.assert_called_once()
