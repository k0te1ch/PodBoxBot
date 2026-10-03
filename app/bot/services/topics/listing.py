"""Как список выглядит текстом и как из текста понять, что удалить.

Список — нумерованные строки ``1) ВОПРОС - текст``, а в rich-сообщении
таблица: номер, тип, текст, автор и когда добавлено. Длинный список режется на
несколько сообщений, нумерация сквозная. Пункт, отмеченный к удалению
кнопкой под списком, получает значок :data:`MARK` перед номером и
зачёркивается: ``🗑 1) ВОПРОС - текст``. Удаление: «удали 1, 3, 4», «удали
пункты 2-5» или аргументы команды ``/done 1 3 4``.
"""

import html
import re
from dataclasses import dataclass
from datetime import datetime

from services.i18n import DEFAULT_LOCALE, t
from services.topics.models import Item

# Запас до лимита Telegram в 4096 символов: текст экранируется для HTML.
MAX_PAGE_CHARS = 3500
# Под каждым сообщением кнопка на пункт, а кнопок в клавиатуре не больше 100.
MAX_PAGE_ITEMS = 40
MAX_RANGE = 500
# Значок пункта, отмеченного к удалению: в тексте списка, на кнопке с его
# номером и на кнопке «Удалить отмеченные». Меняется в одном месте.
MARK = "🗑 "

_NUMBER = r"\d+(?:\s*[-–—]\s*\d+)?"
_SEPARATOR = r"(?:\s*[,;]\s*|\s+(?:и|and)\s+|\s+)"
_NUMBERS = rf"{_NUMBER}(?:{_SEPARATOR}{_NUMBER})*"
_VERB = r"(?:удали(?:ть)?|убери|убрать|вычеркни|вычеркнуть|обсудили|delete|remove)"
_NOUN = r"(?:пункт(?:ы|а|ов)?|номер(?:а|ов)?|№|#)"
_REMOVAL = re.compile(rf"\s*{_VERB}\s*{_NOUN}?\s*:?\s*({_NUMBERS})\s*[.!]?\s*", re.IGNORECASE)
_ONLY_NUMBERS = re.compile(rf"\s*({_NUMBERS})\s*")
_RANGE = re.compile(r"(\d+)(?:\s*[-–—]\s*(\d+))?")
_NUMBERED_LINE = re.compile(rf"(?:{re.escape(MARK)})?(\d+)\) (.*)")


@dataclass
class Page:
    """Одно сообщение списка: текст, номера пунктов в нём и то же таблицей."""

    text: str
    numbers: list[int]
    html: str = ""
    """Rich-вариант сообщения (:mod:`utils.rich`); *text* его запасной вид."""


def kind_label(item: Item, locale: str = DEFAULT_LOCALE) -> str:
    return t(f"topics_kind_{item.kind}", locale)


def item_text(item: Item, locale: str = DEFAULT_LOCALE) -> str:
    """Пункт без номера: ``ВОПРОС - текст``, годится для HTML."""
    return f"{kind_label(item, locale)} - {html.escape(item.text)}"


def item_line(number: int, item: Item, locale: str = DEFAULT_LOCALE) -> str:
    return f"{number}) {item_text(item, locale)}"


def _when(item: Item, timezone) -> str:
    """Когда пункт добавили: «03.10 14:05» во времени бота."""
    return datetime.fromtimestamp(item.created_at, timezone).strftime("%d.%m %H:%M")


def table_html(numbered: list[tuple[int, Item]], marked: list[int], locale: str, *, title: bool, timezone=None) -> str:
    """Пункты таблицей для rich-сообщения. Отмеченный к удалению пункт
    получает значок :data:`MARK` у номера и зачёркнутый текст."""
    header = "".join(f"<th>{html.escape(t(f'topics_column_{name}', locale))}</th>" for name in COLUMNS)
    rows = []
    for number, item in numbered:
        text = html.escape(item.text)
        cells = [
            f"{MARK}{number}" if number in marked else str(number),
            kind_label(item, locale),
            f"<s>{text}</s>" if number in marked else text,
            html.escape(item.author.name),
            _when(item, timezone),
        ]
        rows.append("<tr>" + "".join(f"<td>{value}</td>" for value in cells) + "</tr>")
    heading = f"<h4>{html.escape(t('topics_list_heading', locale))}</h4>" if title else ""
    return f"{heading}<table bordered striped><tr>{header}</tr>{''.join(rows)}</table>"


COLUMNS = ("number", "kind", "text", "author", "when")


def list_pages(
    items: list[Item], locale: str = DEFAULT_LOCALE, *, marked: list[int] | None = None, timezone=None
) -> list[Page]:
    """Список по сообщениям; заголовок только в первом. Пустой список: одна
    страница с фразой о том, что он пуст."""
    if not items:
        empty = t("topics_list_empty", locale)
        return [Page(empty, [], f"<p>{html.escape(empty)}</p>")]
    marked = marked or []
    pages = [Page(t("topics_list_title", locale), [])]
    for number, item in enumerate(items, start=1):
        line = item_line(number, item, locale)
        if number in marked:
            line = f"{MARK}{number}) <s>{item_text(item, locale)}</s>"
        page = pages[-1]
        if page.numbers and (len(page.text) + len(line) + 1 > MAX_PAGE_CHARS or len(page.numbers) >= MAX_PAGE_ITEMS):
            page = Page("", [])
            pages.append(page)
        page.text = f"{page.text}\n{line}" if page.text else line
        page.numbers.append(number)
    by_number = dict(enumerate(items, start=1))
    for index, page in enumerate(pages):
        numbered = [(number, by_number[number]) for number in page.numbers]
        page.html = table_html(numbered, marked, locale, title=index == 0, timezone=timezone)
    return pages


def mark_lines(shown: str, marked: list[int]) -> str:
    """Текст сообщения списка с отметками у выбранных к удалению пунктов, в HTML.

    *shown*: текст уже показанного сообщения, каким его отдаёт Telegram (без
    разметки). Строки пунктов узнаются по номеру в начале. Отмеченный пункт
    получает значок :data:`MARK` и зачёркивается, остальные выглядят как
    обычно, заголовок не меняется.
    """
    lines = []
    for line in shown.split("\n"):
        found = _NUMBERED_LINE.fullmatch(line)
        if found is None:
            lines.append(html.escape(line))
            continue
        number, body = found.group(1), html.escape(found.group(2))
        lines.append(f"{MARK}{number}) <s>{body}</s>" if int(number) in marked else f"{number}) {body}")
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
