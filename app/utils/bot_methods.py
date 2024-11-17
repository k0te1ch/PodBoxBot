from pathlib import Path
import zipfile
from loguru import logger
from pathlib import Path
from config import FILES_PATH, LOGS_PATH
import zipfile

# TODO: Рестарт бота


def shutdown_bot():
    exit()


@logger.catch
def get_zip_logs(log_name: str) -> Path | None:
    """
    Creates a ZIP archive of log files from the log directory and returns the path to the archive.
    If an error occurs or there are no logs to archive, it logs the error/warning and returns None.

    Args:
        log_name (str): The name of the ZIP file to create.

    Returns:
        log_zip (Path | None): The path to the created ZIP archive, or None if no logs were found or an error occurred.
    """
    try:
        # Retrieve all log files with the .log extension in the LOGS_PATH directory
        log_files = sorted(LOGS_PATH.glob("*.log"))

        if not log_files:
            logger.warning("No log files found for archiving.")
            return None

        # Define the path for the ZIP archive
        log_zip = FILES_PATH / log_name

        # Create the ZIP archive and write log files into it
        with zipfile.ZipFile(log_zip, mode="w") as archive:
            for log_file in log_files:
                if log_file.is_file():  # Ensure it is a file, not a directory
                    archive.write(log_file, arcname=f"logs/{log_file.name}")

        return log_zip  # Return the path to the created ZIP archive

    except Exception as e:
        # Log the error without interrupting the program
        logger.error(f"Error occurred while creating the log archive: {e}")
        return None
