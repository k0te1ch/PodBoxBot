"""Управление процессом бота и выгрузка логов.

Отправка сообщений живёт в :mod:`utils.messaging`, релиз-ноуты —
в :mod:`utils.release_notes`.
"""

import os
import signal
import sys
import zipfile
from pathlib import Path

from loguru import logger

from config import FILES_PATH, LOGS_PATH


# region Bot methods
def shutdown_bot():
    os.kill(os.getpid(), signal.SIGINT)


def restart_bot():
    # Процесс просто выходит — назад его поднимает restart-политика
    # оркестратора (в docker-compose у бота `restart: always`).
    # exit() — это хелпер из site, доступный не во всяком интерпретаторе.
    sys.exit()


# region Logs methods
@logger.catch
def get_zip_logs(log_name: str) -> Path | None:
    """
    Creates a ZIP archive of log files from the log directory and returns the path to the archive
    If an error occurs or there are no logs to archive, it logs the error/warning and returns None

    Args:
        log_name (str): The name of the ZIP file to create

    Returns:
        log_zip (Path | None): The path to the created ZIP archive, or None if no logs were found or an error occurred
    """
    try:
        log_files = sorted(LOGS_PATH.glob("*.log"))

        if not log_files:
            logger.warning("No log files found for archiving.")
            return None

        log_zip = FILES_PATH / log_name

        with zipfile.ZipFile(log_zip, mode="w") as archive:
            for log_file in log_files:
                if log_file.is_file():  # Ensure it is a file, not a directory
                    archive.write(log_file, arcname=f"logs/{log_file.name}")

        return log_zip  # Return the path to the created ZIP archive

    except Exception as e:
        logger.error(f"Error occurred while creating the log archive: {e}")
        return None
