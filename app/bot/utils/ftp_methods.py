import asyncio
import ftplib

from config import FTP_POSTSHOW_DIR

# Без таймаута зависший FTP держал бы поток и диалог бесконечно.
FTP_TIMEOUT = 30


NO_REPLY = "no_reply"
REFUSED = "refused"
NO_DIRECTORY = "no_directory"


class EpisodeNumberError(RuntimeError):
    """Номер эпизода не удалось узнать: FTP недоступен или отказал.

    ``reason`` говорит, что именно случилось, чтобы бот не писал «FTP не
    ответил», когда сервер ответил отказом:

    * ``no_reply``: соединения нет (сеть, таймаут, обрыв);
    * ``refused``: сервер ответил ошибкой (логин, права);
    * ``no_directory``: нет каталога послешоу, он в ``directory``.
    """

    def __init__(self, message: str, reason: str = NO_REPLY, directory: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.directory = directory


class _NoDirectoryError(Exception):
    """Сервер не пустил в каталог послешоу."""


def _episode_files(file_list: list[str], type_podcast: str) -> list[str]:
    marker = "_postshow_" if "aftershow" in type_podcast else "_rz_"
    return [x for x in file_list if marker in x and ".mp3" in x and x.split("_")[0].isdigit()]


def _read_last_post_id(type_podcast: str, server: str, login: str, password: str) -> str:
    with ftplib.FTP_TLS(server, login, password, encoding="utf-8", timeout=FTP_TIMEOUT) as ftp:
        if "aftershow" in type_podcast:
            try:
                ftp.cwd(FTP_POSTSHOW_DIR)
            except ftplib.error_perm as e:
                raise _NoDirectoryError(str(e)) from e
        file_list = _episode_files(ftp.nlst(), type_podcast)

    # Пустой каталог (например, первое послешоу в новом FTP_POSTSHOW_DIR):
    # следующим будет первый эпизод.
    if not file_list:
        return "0"
    # По числу, а не по строке: иначе "999_…" > "1000_…", и номера с разной
    # шириной (600 и 0999) сравниваются неверно.
    last_id = max(file_list, key=lambda x: int(x.split("_")[0]))
    return last_id.split("_")[0]


async def get_last_post_id(type_podcast: str, server: str, login: str, password: str) -> str:
    """Возвращает номер последнего эпизода на FTP, ``"0"`` для пустого каталога.

    Сбой FTP (сеть, авторизация, нет каталога) поднимает :class:`EpisodeNumberError`.
    """
    try:
        return await asyncio.to_thread(_read_last_post_id, type_podcast, server, login, password)
    except _NoDirectoryError as e:
        # Каталог не создаём сами: опечатка в FTP_POSTSHOW_DIR иначе начала бы
        # нумерацию послешоу с первого выпуска.
        raise EpisodeNumberError(f"error_perm: {e}", NO_DIRECTORY, FTP_POSTSHOW_DIR) from e
    except ftplib.Error as e:
        raise EpisodeNumberError(f"{type(e).__name__}: {e}", REFUSED) from e
    except ftplib.all_errors as e:
        raise EpisodeNumberError(f"{type(e).__name__}: {e}") from e
