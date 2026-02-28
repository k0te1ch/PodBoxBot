from loguru import logger

from services.kafka.router import router
from services.telegram_updater import telegram_updater


@router.register("progress")
async def handle_progress_event(event):
    await telegram_updater.update_upload_progress(event)


@router.register("result")
async def handle_result_event(event):
    await telegram_updater.update_upload_progress(event, finished=True)
