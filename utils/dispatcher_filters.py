from aiogram.dispatcher.filters import ChatTypeFilter
from aiogram.types import ChatType, Message

from bot import context
from config import ADMINS, LANGUAGES


def IsGroup(m):
    """
    This filter checks whether the chat is group or super group
    :return: bool
    """
    return ChatTypeFilter([ChatType.GROUP, ChatType.SUPER_GROUP])


def IsPrivate(m):
    """
    This filter checks whether the chat is private
    :return: bool
    """
    return ChatTypeFilter(ChatType.PRIVATE)


def IsChannel(m):
    """
    This filter checks whether the chat is a channel
    :return: bool
    """
    return ChatTypeFilter(ChatType.CHANNEL)


def IsAdmin(m):
    """
    This filter checks whether the user is an administrator (in the list of administrators in the settings)
    :return: bool
    """
    return (m.from_user.username in ADMINS)


def ContextButton(context_key: any, classes: list = LANGUAGES):
    """
    This filter checks button's text when have a multi-language context
    example: ContextButton("cancel", ["ru", "en"])
    """
    def inner(m):
        if not(isinstance(m, Message) and m.text):
            return

        for cls in classes:
            if type(context_key) == str:
                contexts = [context_key]
            else:
                contexts = context_key
            for context1 in contexts:
                attr = getattr(context[cls], context1)
                if type(attr) == list:
                    for i in attr:
                        if m.text == i:
                            return True
                else:
                    if m.text == attr:
                        return True
    return inner
