"""Вложения сообщения, которое стало пунктом списка.

Фото закрепляется за пунктом и встаёт в список. Видео, файлы и прочее
тяжёлое в список не тянем: пункт получает ссылку на сообщение в Telegram.
Ссылка строится только из публичных данных чата (username или id
супергруппы), токены и file_id в неё не попадают.
"""

import re

from aiogram.enums import ChatType
from aiogram.types import Message

_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}")
_PRIVATE_PREFIX = "-100"
_LINKED_CHATS = (ChatType.SUPERGROUP, ChatType.CHANNEL)


def message_link(message: Message) -> str | None:
    """Ссылка на сообщение: ``t.me/<username>/<id>`` или ``t.me/c/<id>/<id>``.

    Для личных чатов и обычных групп ссылки нет: ``None``.
    """
    chat = message.chat
    if chat.type not in _LINKED_CHATS:
        return None
    if chat.username and _USERNAME.fullmatch(chat.username):
        return f"https://t.me/{chat.username}/{message.message_id}"
    if str(chat.id).startswith(_PRIVATE_PREFIX):
        return f"https://t.me/c/{str(chat.id)[len(_PRIVATE_PREFIX) :]}/{message.message_id}"
    return None


def photo_of(message: Message) -> str | None:
    """``file_id`` самого большого размера фото."""
    return message.photo[-1].file_id if message.photo else None


def is_heavy(message: Message) -> bool:
    return any((message.video, message.animation, message.document, message.video_note, message.audio, message.voice))


def attachments(*messages: Message | None) -> tuple[str | None, str | None]:
    """Фото и ссылка на тяжёлое вложение из сообщений по порядку важности.

    Берётся первое фото и первое сообщение с тяжёлым вложением: так подпись
    с хештегом и фото, на которое она отвечает, работают одинаково.
    """
    found = [message for message in messages if message is not None]
    photo = next((file_id for file_id in map(photo_of, found) if file_id), None)
    heavy = next((message for message in found if is_heavy(message)), None)
    return photo, message_link(heavy) if heavy is not None else None
