"""Сбор коротких записей по хештегам: заметки ведущих и вопросы слушателей.

Пакет не знает ни про меню, ни про конкретный бот: хештеги разбираются в
:mod:`.hashtags`, записи лежат в Redis через :class:`.store.EntryStore`.
Так его можно перенести в sagenza-tgbot-sdk целиком, поменяв только импорт.
"""

from services.collector.hashtags import extract_hashtags, pick_tag, strip_hashtags
from services.collector.store import Entry, EntryStore

__all__ = ["Entry", "EntryStore", "extract_hashtags", "pick_tag", "strip_hashtags"]
