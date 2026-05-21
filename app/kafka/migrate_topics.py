import os

import yaml
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
from loguru import logger


def load_topics_config(file_path: str) -> list[NewTopic]:
    with open(file_path) as f:
        data = yaml.safe_load(f)

    topics = []
    for topic_cfg in data.get("topics", []):
        topic = NewTopic(
            name=topic_cfg["name"],
            num_partitions=topic_cfg.get("partitions", 1),
            replication_factor=topic_cfg.get("replication_factor", 1),
            topic_configs={k: str(v) for k, v in topic_cfg.get("config", {}).items()},
        )
        topics.append(topic)
    return topics


def create_topics(admin: KafkaAdminClient, topics: list[NewTopic]) -> None:
    for topic in topics:
        try:
            admin.create_topics(new_topics=[topic], validate_only=False)
            logger.success(f"Topic created: {topic.name}")
        except TopicAlreadyExistsError:
            logger.info(f"Topic already exists, skipping: {topic.name}")
        except Exception as e:
            logger.error(f"Failed to create topic {topic.name}: {e}")
            raise


def main() -> None:
    kafka_server = os.getenv("KAFKA_SERVER", "kafka:9092")
    topics_file = os.getenv("TOPICS_FILE", "./topics.yaml")

    logger.info(f"Connecting to Kafka at {kafka_server}")
    admin = KafkaAdminClient(bootstrap_servers=kafka_server)
    topics = load_topics_config(topics_file)

    logger.info(f"Starting Kafka topic migration ({len(topics)} topics)")
    create_topics(admin, topics)
    admin.close()
    logger.info("Kafka topic migration finished")


if __name__ == "__main__":
    main()
