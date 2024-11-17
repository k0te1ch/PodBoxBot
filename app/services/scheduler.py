from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import TIMEZONE
from loguru import logger
from redis.asyncio import Redis
from services.none_module import _NoneModule
from services.redis import redis


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

    scheduler = AsyncIOScheduler(jobstores=jobstores, job_defaults=job_defaults, timezone=TIMEZONE)

    logger.debug(f"Scheduler configured with jobstores: {jobstores}")
    return scheduler


async def init_scheduler_jobs() -> None:
    """
    Инициализация задач для планировщика
    """

    from datetime import date, datetime, time, timedelta

    from apscheduler.triggers.cron import CronTrigger
    from handlers.schedule_handler import next_day, next_para
    from utils import scheduleParser

    try:
        for time_str in await scheduleParser.get_time():
            time_list = time_str.split(" - ")

            hour_start, minute_start = map(int, time_list[0].split(":"))
            start = datetime.combine(date.today(), time(hour=hour_start, minute=minute_start)) - timedelta(minutes=5)
            try:
                scheduler.add_job(
                    next_para,
                    trigger=CronTrigger(hour=start.hour, minute=start.minute, timezone=TIMEZONE),
                    args=[time_list[0]],
                    name=f"para-{time_list[0]}",
                    replace_existing=True,
                    timezone=TIMEZONE,
                )
            except JobLookupError as e:
                logger.error(f"Error adding job para-{time_list[0]}: {str(e)}")

        try:
            scheduler.add_job(
                next_day,
                trigger=CronTrigger(hour=0, timezone=TIMEZONE),
                name="next_day",
                replace_existing=True,
                timezone=TIMEZONE,
            )
        except JobLookupError as e:
            logger.error(f"Error adding job next_day: {str(e)}")

        try:
            scheduler.add_job(
                scheduleParser.updateTable,
                "interval",
                name="Update table",
                replace_existing=True,
                seconds=600,
                timezone=TIMEZONE,
            )

        except JobLookupError as e:
            logger.error(f"Error adding job Update table: {str(e)}")

        logger.success("Scheduler jobs initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler jobs: {str(e)}")


scheduler: AsyncIOScheduler = _get_scheduler_obj(redis)
