import asyncio
import ftplib

from loguru import logger

from shared.kafka.consumer import KafkaConsumer
from shared.kafka.models.upload_event import UploadEvent
from shared.kafka.producer import KafkaProducer

# Kafka topics and config
UPLOAD_TOPIC = "publisher.ftp.upload"
RESULT_TOPIC = "publisher.ftp.result"
KAFKA_SERVER = "kafka:9092"
SCHEMA_REGISTRY_URL = "http://schema-registry:8081"
VALUE_SCHEMA_PATH = "shared/kafka/schemas/upload_event.avsc"


async def send_upload_request(producer: KafkaProducer, path: str, file_name: str, user: str = "system"):
    """Отправляет событие UploadEvent в Kafka"""
    event = UploadEvent(
        event_type="request",
        file_name=file_name,
        path=path,
        username=user,
    )

    logger.info(f"[Kafka] Sending upload request for {event.file_name}")
    await producer.send(UPLOAD_TOPIC, event.model_dump())


async def listen_for_result(file_name: str, timeout: int = 30):
    """Слушает Kafka topic и отслеживает прогресс загрузки"""
    consumer = KafkaConsumer(
        kafka_server=KAFKA_SERVER,
        schema_registry_url=SCHEMA_REGISTRY_URL,
        topic=RESULT_TOPIC,
        group_id="publisher.ftp.result.group",
    )

    async def handler(payload: dict):
        try:
            event = UploadEvent(**payload)
        except Exception as e:
            logger.error(f"[Kafka] Invalid message structure: {e}")
            return

        if event.file_name != file_name:
            return

        if event.status == "uploading":
            logger.info(
                f"[{event.file_name}] progress={event.progress * 100:.1f}% "
                f"speed={event.transfer_speed / 1024:.2f} KB/s"
            )
        elif event.status == "success":
            logger.success(f"[{event.file_name}] upload completed successfully ✅")
        elif event.status == "failure":
            err = event.metadata.get("error") if event.metadata else "unknown"
            logger.error(f"[{event.file_name}] upload failed ❌: {err}")
        else:
            logger.debug(f"[{event.file_name}] Unknown status: {event.status}")

    try:
        logger.info(f"[Kafka] Listening for upload result for {file_name}")
        task = asyncio.create_task(consumer.listen(handler))
        await asyncio.wait_for(task, timeout=timeout)
    except TimeoutError:
        logger.warning(f"[Kafka] Timeout waiting for upload result: {file_name}")
    finally:
        logger.info(f"[Kafka] Stopped listening for {file_name}")


async def get_last_post_ID(typePodcast: str, server: str, login: str, password: str) -> str:
    """Возвращает последний ID файла на FTP"""
    with ftplib.FTP_TLS(server, login, password, encoding="utf-8") as FTP:
        if "aftershow" in typePodcast:
            FTP.cwd("postshow")  # TODO: вынести в настройки

        file_list: list[str] = FTP.nlst()

        if "aftershow" not in typePodcast:
            file_list = filter(
                lambda x: "_rz_" in x and ".mp3" in x and x.split("_")[0].isdigit(),
                file_list,
            )
        else:
            file_list = filter(
                lambda x: "_postshow_" in x and ".mp3" in x and x.split("_")[0].isdigit(),
                file_list,
            )

        last_id = sorted(file_list)[-1]
        return last_id.split("_")[0]
