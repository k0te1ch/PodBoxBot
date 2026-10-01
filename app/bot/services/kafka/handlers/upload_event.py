from loguru import logger

from services.kafka.router import router
from services.metrics import bot_metrics


@router.register("progress")
async def handle_progress_event(event):
    from services import telegram_updater

    await telegram_updater.update_upload_progress(event)


@router.register("result")
async def handle_result_event(event):
    """Итог публикации. Успехом считается только явный ``status="success"``."""
    from services import telegram_updater

    status = event.get("status")

    if status == "success":
        await telegram_updater.update_upload_result(event, success=True)
    elif status == "failure":
        error = event.get("error", "Неизвестная ошибка")
        await telegram_updater.update_upload_result(event, success=False, error=error)
    elif status == "retrying":
        await telegram_updater.update_upload_retry(event)
    else:
        logger.warning(f"Result event with unknown status {status!r} ignored: {event}")


async def record_publish_metrics(event: dict, platform: str) -> None:
    """Итог публикации в метриках: успех, ошибка по шагу или повтор.

    ``platform`` задаёт топик, из которого пришло событие: в самом событии
    площадка есть не всегда.
    """
    if event.get("event_type") != "result":
        return
    status = event.get("status")
    metadata = event.get("metadata") or {}
    type_episode = event.get("type_episode")
    if status == "success":
        await bot_metrics.publish_succeeded(
            platform,
            type_episode,
            metadata.get("action"),
            number=event.get("number"),
            file_name=event.get("file_name"),
        )
    elif status == "failure":
        bot_metrics.publish_failed(platform, type_episode, metadata.get("stage"))
    elif status == "retrying":
        bot_metrics.publish_retry(platform, metadata.get("stage"))
