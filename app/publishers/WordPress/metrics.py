from aioprometheus import Counter, Summary
from aioprometheus.collectors import Registry
from aioprometheus.pusher import Pusher
from loguru import logger
from shared.config import config

PUSHGATEWAY_URL = config.get("PUSHGATEWAY_URL", str, default="http://localhost:9091")

registry = Registry()
wp_upload_success_counter = Counter(
    "wp_upload_success_total",
    "Total successful WordPress uploads",
    registry=registry,
)
wp_upload_failure_counter = Counter(
    "wp_upload_failure_total",
    "Total failed WordPress uploads",
    registry=registry,
)
wp_upload_duration = Summary(
    "wp_upload_duration_seconds",
    "Duration of WordPress upload in seconds",
    registry=registry,
)


async def push_metrics(job: str, registry: Registry):
    try:
        pusher = Pusher(job_name=job, addr=PUSHGATEWAY_URL)
        await pusher.add(registry=registry)
        logger.debug("Metrics pushed to Pushgateway")
    except Exception as e:
        logger.warning(f"Failed to push metrics: {e}")
