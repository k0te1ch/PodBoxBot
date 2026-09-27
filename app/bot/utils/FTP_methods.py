import ftplib

from loguru import logger

from config import FTP_POSTSHOW_DIR
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


async def get_last_post_ID(typePodcast: str, server: str, login: str, password: str) -> str:
    """Возвращает последний ID файла на FTP"""
    with ftplib.FTP_TLS(server, login, password, encoding="utf-8") as FTP:
        if "aftershow" in typePodcast:
            FTP.cwd(FTP_POSTSHOW_DIR)

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

        # По числу, а не по строке: иначе "999_…" > "1000_…", и номера с разной
        # шириной (600 и 0999) сравниваются неверно.
        last_id = max(file_list, key=lambda x: int(x.split("_")[0]))
        return last_id.split("_")[0]
