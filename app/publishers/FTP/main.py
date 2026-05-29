"""FTP publisher: подписан на publisher.ftp.upload, заливает файл по SFTP,
шлёт прогресс и финальный результат в publisher.ftp.result."""

from __future__ import annotations

import asyncio
import os
import time

import aiofiles
import asyncssh
from loguru import logger

from shared.config import config
from shared.kafka.models.upload_event import UploadEvent
from shared.kafka.producer import KafkaProducer
from shared.publishers.base import BasePublisher

# FTP-config (платформо-специфичный — base его не знает).
FTP_SERVER = config.FTP_SERVER
FTP_LOGIN = config.FTP_LOGIN
FTP_PASSWORD = config.FTP_PASSWORD
FTP_POSTSHOW_DIR = config.FTP_POSTSHOW_DIR


async def upload_to_ftp(
    path: str,
    file_name: str,
    user: str,
    producer: KafkaProducer,
    result_topic: str,
    chat_id: str | None = None,
    message_id: str | None = None,
    type_episode: str | None = None,
) -> None:
    """SFTP-загрузка с эмиссией progress-событий каждые ~5 секунд."""
    file_size = os.path.getsize(path)
    bytes_uploaded = 0
    chunk_size = 64 * 1024  # 64KB
    start_time = time.time()
    last_sent = 0.0

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

                if time.time() - last_sent >= 5:
                    last_sent = time.time()
                    progress_event = UploadEvent(
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
                        type_episode=type_episode,
                    )
                    _task = asyncio.create_task(  # noqa: RUF006
                        producer.send(result_topic, progress_event.model_dump())
                    )
                    logger.debug(f"Sent {bytes_uploaded}/{file_size}")

    duration = time.time() - start_time
    success_event = UploadEvent(
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
        type_episode=type_episode,
    )
    await producer.send(result_topic, success_event.model_dump())
    logger.success(f"Uploaded {file_name} successfully in {duration:.2f}s")


class FtpPublisher(BasePublisher):
    name = "ftp"
    event_cls = UploadEvent
    schema_path = "/app/shared/kafka/schemas/upload_event.avsc"
    upload_topic = config.UPLOAD_TOPIC
    result_topic = config.RESULT_TOPIC
    group_id = "ftp_group"

    async def publish(self, event: UploadEvent) -> None:  # type: ignore[override]
        await upload_to_ftp(
            path=event.path,
            file_name=event.file_name,
            user=event.username,
            producer=self.producer,
            result_topic=self.result_topic,
            chat_id=event.chat_id,
            message_id=event.message_id,
            type_episode=event.type_episode,
        )

    def event_key(self, event: UploadEvent) -> str:  # type: ignore[override]
        return event.file_name

    def build_failure_event(self, event: UploadEvent, error: str):  # type: ignore[override]
        # Полное обнуление progress-полей: failure после частичной загрузки
        # не должно отображать «99% — ошибка», это путает пользователя.
        return UploadEvent(
            event_type="result",
            file_name=event.file_name,
            path=event.path,
            username=event.username,
            status="failure",
            error=error,
            chat_id=event.chat_id,
            message_id=event.message_id,
            type_episode=event.type_episode,
        )


# Singleton-инстанс используется как тестами (через handle_upload-шим), так
# и main-точкой входа. KafkaProducer/KafkaConsumer внутри не подключаются
# до .run() — конструкторы только сохраняют конфиг.
_publisher = FtpPublisher()


async def handle_upload(payload: dict, producer: KafkaProducer | None = None) -> None:
    """Тестовая обёртка над BasePublisher._handle.

    Сохранена для совместимости с tests/unit/publishers/ftp/test_ftp_handler.py,
    который патчит upload_to_ftp и проверяет вызовы producer.send. Подменяем
    producer публишера, чтобы мок из теста увидел вызовы; восстанавливаем
    после.
    """
    if producer is not None:
        original = _publisher.producer
        _publisher.producer = producer
        try:
            await _publisher._handle(payload)
        finally:
            _publisher.producer = original
    else:
        await _publisher._handle(payload)


if __name__ == "__main__":
    asyncio.run(_publisher.run())
