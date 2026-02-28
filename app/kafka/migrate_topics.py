import yaml
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
from loguru import logger
from shared.config import config


def load_topics_config(file_path: str) -> list[NewTopic]:
    with open(file_path) as f:
        data = yaml.safe_load(f)

    topics = []
    for topic_cfg in data.get("topics", []):
        topic = NewTopic(
            name=topic_cfg["name"],
            num_partitions=topic_cfg.get("partitions", 1),
            replication_factor=topic_cfg.get("replication_factor", 1),
            topic_configs=topic_cfg.get("config", {}),
        )
        topics.append(topic)
    return topics


def create_topics(admin: KafkaAdminClient, topics: list[NewTopic]):
    try:
        admin.create_topics(new_topics=topics, validate_only=False)
        for topic in topics:
            logger.success(f"Topic created: {topic.name}")
    except TopicAlreadyExistsError as e:
        logger.warning(f"Some topics already exist: {e}")
    except Exception as e:
        logger.error(f"Failed to create topics: {e}")


def main():
    kafka_server = config.get("KAFKA_SERVER", str)
    topics_file = "./kafka/topics.yaml"

    admin = KafkaAdminClient(bootstrap_servers=kafka_server)
    topics = load_topics_config(topics_file)

    logger.info("Starting Kafka topic migration")
    create_topics(admin, topics)
    admin.close()
    logger.info("Kafka topic migration finished")


if __name__ == "__main__":
    main()
