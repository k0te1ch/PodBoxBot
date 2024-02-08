import ftplib

# TODO remake this like the module for wordpress


# TODO ADD TEST FOR IT
async def uploadToFTP(
    path: str, fileName: str, server: str, login: str, password: str
) -> None:
    # TODO Add logs for the debug level for development
    with ftplib.FTP_TLS(server, login, password, encoding="utf-8") as FTP:
        if "postshow" in fileName:
            FTP.cwd("postshow")  # TODO add to settings

        with open(path, "rb") as file:
            FTP.storbinary(f"STOR {fileName}", file)


# TODO add test about connection
# TODO USE THIS IN HANDLER
async def checkFileFTP(fileName: str, server: str, login: str, password: str) -> bool:
    with ftplib.FTP_TLS(server, login, password, encoding="utf-8") as FTP:
        if "postshow" in fileName:
            FTP.cwd("postshow")  # TODO add to settings
        fileList: list[str] = FTP.nlst()
        for f in fileList:
            if f == fileName:
                return True
        return False


async def getLastPostID(
    typePodcast: str, server: str, login: str, password: str
) -> str:
    with ftplib.FTP_TLS(server, login, password, encoding="utf-8") as FTP:
        if "aftershow" in typePodcast:
            FTP.cwd("postshow")  # TODO add to settings

        fileList: list[str] = FTP.nlst()

        if not "aftershow" in typePodcast:
            fileList = filter(
                lambda x: "_rz_" in x and ".mp3" in x and x.split("_")[0].isdigit(),
                fileList,
            )

        else:
            fileList = filter(
                lambda x: "_postshow_" in x
                and ".mp3" in x
                and x.split("_")[0].isdigit(),
                fileList,
            )  # TODO

        lastID = sorted(fileList)[-1]

        return lastID.split("_")[0]
