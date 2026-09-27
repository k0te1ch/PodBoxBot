from aiogram.enums import ChatType

from config import ADMINS
from filters.chat_type import ChatTypeFilter


async def IsGroup(m) -> bool:
    """
    This filter checks whether the chat is group or super group
    :return: bool
    """
    c = ChatTypeFilter([ChatType.GROUP, ChatType.SUPERGROUP])
    return await c(m)


async def IsPrivate(m) -> bool:
    """
    This filter checks whether the chat is private
    :return: bool
    """
    c = ChatTypeFilter(ChatType.PRIVATE)
    return await c(m)


async def IsChannel(m) -> bool:
    """
    This filter checks whether the chat is a channel
    :return: bool
    """
    c = ChatTypeFilter(ChatType.CHANNEL)
    return await c(m)


def IsAdmin(m) -> bool:
    """
    This filter checks whether the user is an administrator (in the list of administrators in the settings)
    :return: bool
    """
    return m.from_user.username in ADMINS
