from loguru import logger

from services.kafka.router import router


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
