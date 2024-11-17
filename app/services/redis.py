from config import REDIS_URL
from loguru import logger
from redis.asyncio import Redis
from services.none_module import _NoneModule


def _get_redis_obj() -> Redis | _NoneModule:
    if REDIS_URL is not None:
        redis = Redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        logger.debug("Redis is configured")
    else:
        redis = _NoneModule("redis", "REDIS_URL")
        logger.debug("Redis isn't configured")

    return redis


redis: Redis | _NoneModule = _get_redis_obj()
