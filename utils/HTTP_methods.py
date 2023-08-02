from loguru import logger

from bot import bot


@logger.catch
async def get_my_ip() -> str:
    """
    Getting the bot's IP address
    :return: str
    """
    session = await bot.get_session()
    async with session.get("https://ipinfo.io/json") as r:
        jdata = await r.json()
        logger.opt(colors=True).debug("Get IP")
        return jdata.get("ip")


@logger.catch
async def downloadFile(url: str,
                       filename: str,
                       chunk_size: int = 65536) -> None:
    """
    Deleting a message
    :param: url
    :param: filename
    :param: chunk_size = 65536
    :return: None
    """
    logger.opt(
        colors=True).debug(f"The file started downloading <y>({filename})</y>")
    session = await bot.get_session()
    async with session.get(
            url,
            raise_for_status=True,
    ) as response:
        f = open(filename, 'wb')
        while True:
            chunk = await response.content.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            f.flush()
        f.close()
    logger.opt(
        colors=True).debug(f"<g>File downloaded <y>({filename})</y></g>")
