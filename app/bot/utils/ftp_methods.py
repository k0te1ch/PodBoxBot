import ftplib

from config import FTP_POSTSHOW_DIR


async def get_last_post_id(type_podcast: str, server: str, login: str, password: str) -> str:
    """Возвращает последний ID файла на FTP"""
    with ftplib.FTP_TLS(server, login, password, encoding="utf-8") as ftp:
        if "aftershow" in type_podcast:
            ftp.cwd(FTP_POSTSHOW_DIR)

        file_list: list[str] = ftp.nlst()

        if "aftershow" not in type_podcast:
            file_list = filter(
                lambda x: "_rz_" in x and ".mp3" in x and x.split("_")[0].isdigit(),
                file_list,
            )
        else:
            file_list = filter(
                lambda x: "_postshow_" in x and ".mp3" in x and x.split("_")[0].isdigit(),
                file_list,
            )

        # По числу, а не по строке: иначе "999_…" > "1000_…", и номера с разной
        # шириной (600 и 0999) сравниваются неверно.
        last_id = max(file_list, key=lambda x: int(x.split("_")[0]))
        return last_id.split("_")[0]
