from services.kafka.router import router


@router.register("progress")
async def handle_progress_event(event):
    from services import telegram_updater

    await telegram_updater.update_upload_progress(event)


@router.register("result")
async def handle_result_event(event):
    from services import telegram_updater

    status = event.get("status")

    if status == "success":
        await telegram_updater.update_upload_result(event, success=True)
    elif status == "failure":
        error = event.get("error", "Неизвестная ошибка")
        await telegram_updater.update_upload_result(event, success=False, error=error)
    else:
        # FTP upload finished (legacy format without explicit status)
        await telegram_updater.update_upload_progress(event, finished=True)
