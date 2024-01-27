import ftplib


def shutdown_bot():
    exit()


# TODO ADD TEST FOR IT
async def uploadToFTP(
    path: str, filename: str, server: str, login: str, password: str
) -> None:
    with ftplib.FTP_TLS(server, login, password, encoding="utf-8") as FTP:
        if "postshow" in filename:
            FTP.cwd("postshow")  # TODO add to settings

        with open(path, "rb") as file:
            FTP.storbinary(f"STOR {filename}", file)


# TODO add test about connection
# TODO USE THIS IN HANDLER
async def checkFileFTP(filename: str, server: str, login: str, password: str) -> bool:
    with ftplib.FTP_TLS(server, login, password, encoding="utf-8") as FTP:
        filelist: list[str] = []
        FTP.retrlines("LIST", filelist.append)
        for f in filelist:
            if f.split()[-1] == filename:
                return True
        return False
