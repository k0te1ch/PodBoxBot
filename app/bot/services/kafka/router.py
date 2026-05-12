# podboxbot/kafka/router.py
from loguru import logger


class KafkaEventRouter:
    def __init__(self):
        self._handlers = {}

    def register(self, event_type: str):
        def decorator(func):
            self._handlers[event_type] = func
            return func

        return decorator

    async def route(self, event):
        event_type = event.get("event_type")
        handler = self._handlers.get(event_type)
        if not handler:
            logger.warning(f"Unhandled Kafka event type: {event_type}")
            return

        try:
            await handler(event)
        except Exception:
            logger.exception(f"Error handling Kafka event: {event_type}")


# Singleton instance — используется хендлерами через import
router = KafkaEventRouter()
