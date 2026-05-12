import asyncio
import time

from loguru import logger
from metrics import (
    push_metrics,
    registry,
    wp_upload_duration,
    wp_upload_failure_counter,
    wp_upload_success_counter,
)
from shared.config import config
from shared.kafka.consumer import KafkaConsumer
from shared.kafka.models.wordpress_event import WordPressEvent
from shared.kafka.producer import KafkaProducer
from wordpress import WordPress

# Kafka config
KAFKA_SERVER = config.get("KAFKA_SERVER", str)
UPLOAD_TOPIC = config.get("WP_UPLOAD_TOPIC", str, default="publisher.wordpress.upload")
RESULT_TOPIC = config.get("WP_RESULT_TOPIC", str, default="publisher.wordpress.result")
GROUP_ID = "wordpress_group"
SCHEMA_REGISTRY_URL = config.get("SCHEMA_REGISTRY_URL", str)
SCHEMA_PATH = "/app/shared/kafka/schemas/wordpress_event.avsc"

# WordPress config
WP_URL = config.get("WP_URL", str)
WP_LOGIN = config.get("WP_LOGIN", str)
WP_PASSWORD = config.get("WP_PASSWORD", str)
WP_COOKIE_PATH = config.get("WP_COOKIE_PATH", str, default="/app/data/cookie.pkl")
TIMEZONE = config.get("TIMEZONE", str, default="Europe/Moscow")


async def handle_upload(payload: dict, producer: KafkaProducer):
    """Обрабатывает событие WordPressEvent"""
    try:
        event = WordPressEvent(**payload)
    except Exception as e:
        logger.error(f"Invalid WordPressEvent payload: {e}")
        return

    logger.info(f"Received WordPress upload request from {event.username} for episode {event.number}")

    start_time = time.time()
    try:
        info = {
            "number": event.number,
            "title": event.title,
            "comment": event.comment,
            "chapters": event.chapters,
            "tags": event.tags,
            "slug": event.slug,
            "duration": event.duration,
        }

        with WordPress(WP_URL, WP_LOGIN, WP_PASSWORD, WP_COOKIE_PATH, TIMEZONE) as wp:
            success = wp.upload_post(info)

        if success:
            wp_upload_success_counter.inc({"episode": event.number})
            result_event = WordPressEvent(
                event_type="result",
                username=event.username,
                status="success",
                chat_id=event.chat_id,
                message_id=event.message_id,
                number=event.number,
                title=event.title,
                comment=event.comment,
                chapters=event.chapters,
                tags=event.tags,
                slug=event.slug,
                duration=event.duration,
            )
        else:
            wp_upload_failure_counter.inc({"episode": event.number})
            result_event = WordPressEvent(
                event_type="result",
                username=event.username,
                status="failure",
                error="WordPress returned non-success response",
                chat_id=event.chat_id,
                message_id=event.message_id,
                number=event.number,
                title=event.title,
                comment=event.comment,
                chapters=event.chapters,
                tags=event.tags,
                slug=event.slug,
                duration=event.duration,
            )

        await producer.send(RESULT_TOPIC, result_event.model_dump())
        logger.success(f"WordPress upload completed for episode {event.number}")

    except Exception as e:
        logger.error(f"Failed to upload episode {event.number} to WordPress: {e}")
        wp_upload_failure_counter.inc({"episode": event.number})

        failure_event = WordPressEvent(
            event_type="result",
            username=event.username,
            status="failure",
            error=str(e),
            chat_id=event.chat_id,
            message_id=event.message_id,
            number=event.number,
            title=event.title,
            comment=event.comment,
            chapters=event.chapters,
            tags=event.tags,
            slug=event.slug,
            duration=event.duration,
        )
        await producer.send(RESULT_TOPIC, failure_event.model_dump())
    finally:
        wp_upload_duration.observe(
            {"episode": event.number, "user": event.username},
            time.time() - start_time,
        )
        await push_metrics("wordpress_publisher", registry)


async def consume_loop():
    """Основной Kafka consumer loop"""
    consumer = KafkaConsumer(
        kafka_server=KAFKA_SERVER,
        schema_registry_url=SCHEMA_REGISTRY_URL,
        topic=UPLOAD_TOPIC,
        group_id=GROUP_ID,
    )
    producer = KafkaProducer(
        kafka_server=KAFKA_SERVER,
        schema_registry_url=SCHEMA_REGISTRY_URL,
        value_schema_path=SCHEMA_PATH,
    )

    async def handler(payload):
        await handle_upload(payload, producer)

    await consumer.start(handler)


if __name__ == "__main__":
    asyncio.run(consume_loop())
