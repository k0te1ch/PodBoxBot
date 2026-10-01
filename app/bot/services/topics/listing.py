"""Как список выглядит текстом и как из текста понять, что удалить.

Список — нумерованные строки ``1) ВОПРОС - текст``. Длинный список режется на
несколько сообщений, нумерация сквозная. Пункт, отмеченный кнопкой под
списком, получает галочку перед номером: ``✅ 1) ВОПРОС - текст``. Удаление:
«удали 1, 3, 4», «удали пункты 2-5» или аргументы команды ``/done 1 3 4``.
"""

import html
import re
from dataclasses import dataclass

from services.i18n import DEFAULT_LOCALE, t
from services.topics.models import Item

# Запас до лимита Telegram в 4096 символов: текст экранируется для HTML.
MAX_PAGE_CHARS = 3500
# Под каждым сообщением кнопка на пункт, а кнопок в клавиатуре не больше 100.
MAX_PAGE_ITEMS = 40
MAX_RANGE = 500
MARK = "✅ "

_NUMBER = r"\d+(?:\s*[-–—]\s*\d+)?"
_SEPARATOR = r"(?:\s*[,;]\s*|\s+(?:и|and)\s+|\s+)"
_NUMBERS = rf"{_NUMBER}(?:{_SEPARATOR}{_NUMBER})*"
_VERB = r"(?:удали(?:ть)?|убери|убрать|вычеркни|вычеркнуть|обсудили|delete|remove)"
_NOUN = r"(?:пункт(?:ы|а|ов)?|номер(?:а|ов)?|№|#)"
_REMOVAL = re.compile(rf"\s*{_VERB}\s*{_NOUN}?\s*:?\s*({_NUMBERS})\s*[.!]?\s*", re.IGNORECASE)
_ONLY_NUMBERS = re.compile(rf"\s*({_NUMBERS})\s*")
_RANGE = re.compile(r"(\d+)(?:\s*[-–—]\s*(\d+))?")
_NUMBERED_LINE = re.compile(rf"(?:{MARK})?(\d+)\) ")


@dataclass
class Page:
    """Одно сообщение списка: текст и номера пунктов в нём."""

    text: str
    numbers: list[int]


def kind_label(item: Item, locale: str = DEFAULT_LOCALE) -> str:
    return t(f"topics_kind_{item.kind}", locale)


def item_text(item: Item, locale: str = DEFAULT_LOCALE) -> str:
    """Пункт без номера: ``ВОПРОС - текст``, годится для HTML."""
    return f"{kind_label(item, locale)} - {html.escape(item.text)}"


def item_line(number: int, item: Item, locale: str = DEFAULT_LOCALE) -> str:
    return f"{number}) {item_text(item, locale)}"


def list_pages(items: list[Item], locale: str = DEFAULT_LOCALE) -> list[Page]:
    """Список по сообщениям; заголовок только в первом. Пустой список: одна
    страница с фразой о том, что он пуст."""
    if not items:
        return [Page(t("topics_list_empty", locale), [])]
    pages = [Page(t("topics_list_title", locale), [])]
    for number, item in enumerate(items, start=1):
        line = item_line(number, item, locale)
        page = pages[-1]
        if page.numbers and (len(page.text) + len(line) + 1 > MAX_PAGE_CHARS or len(page.numbers) >= MAX_PAGE_ITEMS):
            page = Page("", [])
            pages.append(page)
        page.text = f"{page.text}\n{line}" if page.text else line
        page.numbers.append(number)
    return pages


def mark_lines(shown: str, marked: list[int]) -> str:
    """Текст сообщения списка с галочками у отмеченных пунктов, в HTML.

    *shown*: текст уже показанного сообщения, каким его отдаёт Telegram (без
    разметки). Строки пунктов узнаются по номеру в начале; у отмеченных
    появляется галочка, у остальных она снимается, заголовок не меняется.
    """
    lines = []
    for line in shown.split("\n"):
        found = _NUMBERED_LINE.match(line)
        if found:
            plain = line.removeprefix(MARK)
            line = f"{MARK}{plain}" if int(found.group(1)) in marked else plain
        lines.append(html.escape(line))
    return "\n".join(lines)


def _expand(raw: str) -> list[int] | None:
    numbers: list[int] = []
    for start, end in _RANGE.findall(raw):
        first, last = int(start), int(end or start)
        if first < 1 or last < first or last - first >= MAX_RANGE:
            return None
        numbers += [n for n in range(first, last + 1) if n not in numbers]
    return numbers or None


def parse_numbers(raw: str | None) -> list[int] | None:
    """«1 3 4», «1, 3-5 и 7» → номера по порядку, без повторов; иначе ``None``."""
    match = _ONLY_NUMBERS.fullmatch(raw or "")
    return _expand(match.group(1)) if match else None


def parse_removal(text: str | None) -> list[int] | None:
    """Номера из «удали 1, 3, 4»; ``None``, если это не просьба удалить."""
    match = _REMOVAL.fullmatch(text or "")
    return _expand(match.group(1)) if match else None
