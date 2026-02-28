from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from redis.asyncio import Redis

from config import TIMEZONE
from services import redis
from services.none_module import _NoneModule

# TODO: Аннотации
# TODO: Обработка ошибок


def _get_scheduler_obj(redis_instance: Redis | _NoneModule) -> AsyncIOScheduler:
    job_defaults = {"misfire_grace_time": 3600}

    if not isinstance(redis_instance, _NoneModule):
        cfg = redis_instance.connection_pool.connection_kwargs
        jobstores = {
            "default": RedisJobStore(
                host=cfg.get("host", "localhost"),
                port=cfg.get("port", 6379),
                db=cfg.get("db", 0),
                password=cfg.get("password"),
            )
        }
    else:
        jobstores = {"default": MemoryJobStore()}

    scheduler = AsyncIOScheduler(
        jobstores=jobstores, job_defaults=job_defaults, timezone=TIMEZONE
    )

    logger.debug(f"Scheduler configured with jobstores: {jobstores}")
    return scheduler


async def init_scheduler_jobs() -> None:
    """
    Инициализация задач для планировщика
    """


scheduler: AsyncIOScheduler = _get_scheduler_obj(redis)
