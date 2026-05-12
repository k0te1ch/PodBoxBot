"""Tests for the Kafka event router."""

import pytest
from app.bot.services.kafka.router import KafkaEventRouter


class TestKafkaEventRouter:
    def test_register_handler(self):
        router = KafkaEventRouter()

        @router.register("test_event")
        async def handler(event):
            pass

        assert "test_event" in router._handlers
        assert router._handlers["test_event"] is handler

    @pytest.mark.asyncio
    async def test_route_calls_handler(self):
        router = KafkaEventRouter()
        received = []

        @router.register("progress")
        async def handler(event):
            received.append(event)

        await router.route({"event_type": "progress", "data": "test"})
        assert len(received) == 1
        assert received[0]["data"] == "test"

    @pytest.mark.asyncio
    async def test_route_unhandled_event(self, caplog):
        router = KafkaEventRouter()
        await router.route({"event_type": "unknown_type"})
        # Should not raise, just log warning

    @pytest.mark.asyncio
    async def test_route_handler_exception(self, caplog):
        router = KafkaEventRouter()

        @router.register("error_event")
        async def bad_handler(event):
            raise ValueError("Something went wrong")

        # Should not raise, exception is caught
        await router.route({"event_type": "error_event"})

    @pytest.mark.asyncio
    async def test_route_no_event_type(self):
        router = KafkaEventRouter()
        # Should not raise with missing event_type
        await router.route({"some": "data"})

    def test_multiple_handlers(self):
        router = KafkaEventRouter()

        @router.register("type_a")
        async def handler_a(event):
            pass

        @router.register("type_b")
        async def handler_b(event):
            pass

        assert len(router._handlers) == 2
        assert router._handlers["type_a"] is handler_a
        assert router._handlers["type_b"] is handler_b

    @pytest.mark.asyncio
    async def test_result_event_routing(self):
        router = KafkaEventRouter()
        results = {"progress": [], "result": []}

        @router.register("progress")
        async def progress_handler(event):
            results["progress"].append(event)

        @router.register("result")
        async def result_handler(event):
            results["result"].append(event)

        await router.route({"event_type": "progress", "progress": 0.5})
        await router.route({"event_type": "result", "status": "success"})
        await router.route({"event_type": "progress", "progress": 0.8})

        assert len(results["progress"]) == 2
        assert len(results["result"]) == 1
