import asyncio
import os
import time
from collections.abc import AsyncGenerator, Callable
from pathlib import Path

import aiofiles
from aiogram import Bot
from aiogram.types import Message
from aiogram.types.input_file import DEFAULT_CHUNK_SIZE, InputFile
from loguru import logger

from config import LOCAL, PODCAST_PATH

# TODO: Рестарт бота

CHUNK_SIZE = 64 * 1024  # Размер блока 64 КБ


# region Progressbars
class CustomFSInputFile(InputFile):
    def __init__(
        self,
        path: str | Path,
        filename: str | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        progress_callback: Callable[[int], None] | None = None,
    ):
        """
        Represents object for uploading files from filesystem with progress tracking

        :param path: Path to file
        :param filename: Filename to be propagated to telegram
            By default, will be parsed from path
        :param chunk_size: Uploading chunk size
        :param progress_callback: Callable to track progress, receives number of bytes read
        """
        if filename is None:
            filename = os.path.basename(path)
        super().__init__(filename=filename, chunk_size=chunk_size)

        self.path = path
        self.size = Path(path).stat().st_size
        self.progress_callback = progress_callback

    async def read(self, bot: "Bot") -> AsyncGenerator[bytes, None]:
        async with aiofiles.open(self.path, "rb") as f:
            total_read = 0
            prev_percent = -1

            while True:
                chunk = await f.read(self.chunk_size)
                if not chunk:
                    break

                total_read += len(chunk)
                percent = int((total_read / self.size) * 100)

                # yield chunk перед коллбеком (важно!)
                yield chunk

                if percent >= prev_percent + 10 or percent == 100:
                    prev_percent = percent
                    logger.debug(
                        f"Uploading: {percent:.2f}% ({total_read}/{self.size})"
                    )

                    if self.progress_callback:
                        result = self.progress_callback(total_read)
                        if asyncio.iscoroutine(result):
                            asyncio.create_task(result)

                await asyncio.sleep(0)

            # Гарантируем, что при выходе из файла progress 100%
            if self.progress_callback and prev_percent != percent:
                result = self.progress_callback(self.size)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)

            logger.debug("Upload finished and read() complete")


async def telegram_progress_callback(
    bytes_uploaded: int, message: Message, total_size: int
):
    progress = (bytes_uploaded / total_size) * 100
    now = int(time.time())

    if message.edit_date is None or (now - message.edit_date >= 1):
        await message.edit_text(f"Загрузка файла: {progress:.2f}%")


@logger.catch
async def check_exists_file_by_size(dir_path: Path, file_size: int) -> Path | None:
    """Ищем файл по его размеру

    Args:
            dir_path (Path): Путь к папке, где мы ищем файл
            file_size (int): Размер файла, которго мы ищем в битах

    Returns:
            Path | None: Файл, если сущесвует или None

    Raises:
            NotADirectoryError: dir_path - файл, а не директория
    """
    if not dir_path.is_dir():
        raise NotADirectoryError

    for file in dir_path.iterdir():
        if file.stat().st_size == file_size:
            return file

    return None


@logger.catch
async def monitor_file_progress(
    file_path: Path,
    total_size: int,
    progress_callback: Callable[[int, int], None],
    finally_dir_path: Path,
    poll_interval: float = 0.5,
) -> True | False:
    """
    Отслеживает прогресс скачивания файла, мониторя файловую систему

    :param file_path: Путь к файлу, который загружается
    :param total_size: Общий размер файла в байтах
    :param progress_callback: Callback для отслеживания прогресса
    :param poll_interval: Интервал опроса файловой системы (в секундах)
    :return bool: Возвращает True при успехе или False при неудаче
    """
    logger.debug("Monitor task created")

    dots_cycle = iter([".", "..", "...", ""])
    downloaded_size = 0
    mp3_file = None
    checked = False

    if file_path.is_file() and not LOCAL:
        mp3_file = file_path
        logger.debug(f"Используем переданный файл: {mp3_file.name}")

    while downloaded_size < total_size:
        try:
            # Поиск файла, если он ещё не был определён
            if not mp3_file:
                logger.debug(f"Ищем скачивающийся файл{next(dots_cycle)}")
                for file in file_path.iterdir():
                    if file.is_file() and file.stem.isdigit():
                        mp3_file = file
                        logger.debug(f"Найден файл: {mp3_file.name}")
                        break

            # Отслеживание прогресса файла
            if mp3_file and mp3_file.exists():
                prev_downloaded_size = downloaded_size
                downloaded_size = mp3_file.stat().st_size
                if downloaded_size != prev_downloaded_size:
                    logger.debug(
                        f"Текущий размер файла: {downloaded_size} из {total_size}"
                    )
                    await progress_callback(downloaded_size)
            elif mp3_file and not mp3_file.exists():
                if PODCAST_PATH.exists():
                    mp3_file = PODCAST_PATH
                else:
                    if await check_exists_file_by_size(finally_dir_path, total_size):
                        checked = True
                        break
                    raise FileNotFoundError("Файл исчез")

            await asyncio.sleep(poll_interval)

        except Exception as e:
            logger.error(f"Ошибка при отслеживании файла: {e}")
            break

    # Завершение мониторинга
    if (
        downloaded_size >= total_size
        or checked
        or (await check_exists_file_by_size(finally_dir_path, total_size))
    ):
        logger.info("Файл полностью загружен!")
        return True
    else:
        logger.warning("Мониторинг завершён, но файл не достиг полного размера")
        return False
