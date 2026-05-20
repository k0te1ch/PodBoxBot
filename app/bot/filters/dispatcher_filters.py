from aiogram.enums import ChatType
from aiogram.types import Message

from config import ADMINS, LANGUAGES
from filters.chat_type import ChatTypeFilter
from services import context


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


def ContextButton(context_key: str | list, classes: list = LANGUAGES):
    keys = [context_key] if isinstance(context_key, str) else context_key

    def inner(m) -> bool | None:
        if not (isinstance(m, Message) and m.text):
            return None
        for cls in classes:
            for key in keys:
                attr = getattr(context[cls], key)
                values = attr if isinstance(attr, list) else [attr]
                if m.text in values:
                    return True
        return None

    return inner
