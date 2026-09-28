"""Разбор хештегов в тексте сообщения."""

import re
from collections.abc import Iterable

# Telegram считает хештегом «#» и буквы/цифры/подчёркивание, в том числе
# кириллицу; «#вопрос@bot» тоже хештег, суффикс с ботом отбрасывается.
_HASHTAG = re.compile(r"(?<![\w#])#(\w+)(?:@\w+)?")


def normalize_tag(tag: str) -> str:
    return tag.lstrip("#").strip().lower()


def extract_hashtags(text: str | None) -> list[str]:
    """Хештеги сообщения в нижнем регистре, без «#» и повторов, по порядку."""
    seen: dict[str, None] = {}
    for match in _HASHTAG.finditer(text or ""):
        seen.setdefault(normalize_tag(match.group(1)), None)
    return list(seen)


def pick_tag(text: str | None, allowed: Iterable[str]) -> str | None:
    """Первый хештег сообщения из списка *allowed* или ``None``."""
    wanted = {normalize_tag(tag) for tag in allowed}
    return next((tag for tag in extract_hashtags(text) if tag in wanted), None)


def strip_hashtags(text: str | None, tags: Iterable[str]) -> str:
    """Текст без служебных хештегов *tags*: они уже стали группой записи."""
    drop = {normalize_tag(tag) for tag in tags}

    def _replace(match: re.Match[str]) -> str:
        return "" if normalize_tag(match.group(1)) in drop else match.group(0)

    return re.sub(r"[ \t]{2,}", " ", _HASHTAG.sub(_replace, text or "")).strip()
