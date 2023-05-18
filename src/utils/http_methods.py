from settings import TOKEN
from main import bot


async def getMyIP():
    session = await bot.get_session()
    async with session.get("https://ipinfo.io/json") as r:
        jdata = await r.json()
        return jdata.get("ip")


async def deleteMsg(chat_id, msg_id):
    session = await bot.get_session()
    async with session.get(f'https://api.telegram.org/bot{TOKEN}/deleteMessage?'
                           f'chat_id={chat_id}&message_id={msg_id}'):
        return
    
async def downloadFile(url, filename):
    session = await bot.get_session()
    async with session.get(
        url,
        raise_for_status=True,
    ) as response:
        f = open(filename, 'wb')
        while True:
            chunk = await response.content.read(65536)
            if not chunk:
                break
            f.write(chunk)
            f.flush()
        f.close()