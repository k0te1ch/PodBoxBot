import asyncio

import aiofiles
import aiohttp
from loguru import logger
from main import bot


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
async def downloadFile(url: str, filename: str, chunk_size: int = 65536) -> None:
    """
    Deleting a message
    :param: url
    :param: filename
    :param: chunk_size = 65536
    :return: None
    """
    logger.opt(colors=True).debug(f"The file started downloading <y>({filename})</y>")
    session = await bot.get_session()
    async with session.get(
        url,
        raise_for_status=True,
    ) as response:
        f = open(filename, "wb")
        while True:
            chunk = await response.content.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            f.flush()
        f.close()
    logger.opt(colors=True).debug(f"<g>File downloaded <y>({filename})</y></g>")


async def download_file(url, destination):
    try:
        async with aiohttp.ClientSession() as session, session.get(url) as response:
            if response.status == 200:
                async with aiofiles.open(destination, "wb") as f:
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        await f.write(chunk)
                return True
            else:
                print(f"Error downloading file, status code: {response.status}")
                return False
    except aiohttp.ClientError as e:
        print(f"Aiohttp client error: {e}")
        return False
    except asyncio.CancelledError:
        print("Download was cancelled")
        return False
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False
