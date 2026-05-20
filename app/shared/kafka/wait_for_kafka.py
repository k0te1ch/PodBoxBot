import asyncio

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError
from loguru import logger

RETRY_INTERVAL = 2
MAX_RETRIES = 15


@logger.catch
async def wait_for_kafka(kafka_server: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            producer = AIOKafkaProducer(bootstrap_servers=kafka_server)
            await producer.start()
            await producer.stop()
            logger.info(f"[Kafka]: Connected on attempt {attempt}")
            return
        except KafkaConnectionError:
            logger.warning(f"[Kafka]: Attempt {attempt}/{MAX_RETRIES} failed, retrying...")
            await asyncio.sleep(RETRY_INTERVAL)
    raise RuntimeError(f"Failed to connect to Kafka at {kafka_server}")
