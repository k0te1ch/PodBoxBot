import asyncio
import os
import time

import aiofiles
import asyncssh
from loguru import logger
from metrics import (
    push_metrics,
    registry,
    upload_duration,
    upload_failure_counter,
    upload_success_counter,
)

from shared.config import config
from shared.kafka.consumer import KafkaConsumer
from shared.kafka.models.upload_event import UploadEvent
from shared.kafka.producer import KafkaProducer

# Kafka config
KAFKA_SERVER = config.get("KAFKA_SERVER", str)
UPLOAD_TOPIC = config.get("UPLOAD_TOPIC", str)
RESULT_TOPIC = config.get("RESULT_TOPIC", str, default="publisher.ftp.result")
GROUP_ID = "ftp_group"
SCHEMA_REGISTRY_URL = config.get("SCHEMA_REGISTRY_URL", str)
SCHEMA_PATH = "/app/shared/kafka/schemas/upload_event.avsc"

# FTP config
FTP_SERVER = config.get("FTP_SERVER", str)
FTP_LOGIN = config.get("FTP_LOGIN", str)
FTP_PASSWORD = config.get("FTP_PASSWORD", str)
FTP_POSTSHOW_DIR = config.get("FTP_POSTSHOW_DIR", str, default="postshow")


async def upload_to_ftp(
    path: str,
    file_name: str,
    user: str,
    producer: KafkaProducer,
    chat_id: str | None = None,
    message_id: str | None = None,
):
    """Загружает файл на SFTP с отчётом прогресса"""
    file_size = os.path.getsize(path)
    bytes_uploaded = 0
    chunk_size = 64 * 1024  # 64KB
    start_time = time.time()
    last_sent = 0

    logger.debug(f"Connecting to SFTP: {FTP_SERVER} as {FTP_LOGIN}")

    async with (
        asyncssh.connect(
            FTP_SERVER,
            port=2222,
            username=FTP_LOGIN,
            password=FTP_PASSWORD,
            known_hosts=None,
        ) as conn,
        conn.start_sftp_client() as sftp,
        aiofiles.open(path, "rb") as f,
    ):
        async with sftp.open(file_name, "wb") as remote_file:
            while True:
                data = await f.read(chunk_size)
                if not data:
                    break

                await remote_file.write(data)
                bytes_uploaded += len(data)

                elapsed = time.time() - start_time
                speed = bytes_uploaded / elapsed if elapsed > 0 else 0.0
                progress = bytes_uploaded / file_size

                # Каждые 5 сек шлём прогресс
                if time.time() - last_sent >= 5:
                    last_sent = time.time()
                    event = UploadEvent(
                        event_type="progress",
                        file_name=file_name,
                        path=path,
                        username=user,
                        bytes_uploaded=bytes_uploaded,
                        total_bytes=file_size,
                        progress=round(progress, 3),
                        transfer_speed=round(speed, 2),
                        status="uploading",
                        chat_id=chat_id,
                        message_id=message_id,
                    )
                    _task = asyncio.create_task(  # noqa: RUF006
                        producer.send(RESULT_TOPIC, event.model_dump())
                    )
                    logger.debug(f"Sended {bytes_uploaded}/{file_size}")

    duration = time.time() - start_time
    upload_success_counter.inc({"filename": file_name, "ftp_server": FTP_SERVER})

    result_event = UploadEvent(
        event_type="result",
        file_name=file_name,
        path=path,
        username=user,
        bytes_uploaded=file_size,
        total_bytes=file_size,
        progress=1.0,
        transfer_speed=round(file_size / duration, 2),
        status="success",
        chat_id=chat_id,
        message_id=message_id,
    )
    await producer.send(RESULT_TOPIC, result_event.model_dump())

    logger.success(f"Uploaded {file_name} successfully in {duration:.2f}s")


async def handle_upload(payload: dict, producer: KafkaProducer):
    """Обрабатывает событие UploadEvent"""
    try:
        event = UploadEvent(**payload)  # ✅ валидация через модель
    except Exception as e:
        logger.error(f"Invalid UploadEvent payload: {e}")
        return

    logger.info(f"Received upload request from {event.username} for {event.file_name}")

    start_time = time.time()
    try:
        await upload_to_ftp(
            path=event.path,
            file_name=event.file_name,
            user=event.username,
            producer=producer,
            chat_id=event.chat_id,
            message_id=event.message_id,
        )
    except Exception as e:
        logger.error(f"Failed to upload {event.file_name}: {e}")
        upload_failure_counter.inc({"filename": event.file_name, "ftp_server": FTP_SERVER})

        failure_event = UploadEvent(
            event_type="result",
            file_name=event.file_name,
            path=event.path,
            username=event.username,
            status="failure",
            error=str(e),
            chat_id=event.chat_id,
            message_id=event.message_id,
        )
        await producer.send(RESULT_TOPIC, failure_event.model_dump())
    finally:
        upload_duration.observe(
            {"filename": event.file_name, "user": event.username},
            time.time() - start_time,
        )
        await push_metrics("ftp_uploader", registry)


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
