import re
from datetime import datetime
from pathlib import Path

from loguru import logger

# Дата записи в шаблоне: принимаем DD.MM.YYYY (также /, - как разделители),
# нормализуем в ISO YYYY-MM-DD — именно этот формат ждёт Podlove.
_RECORDING_DATE_RE = re.compile(r"^[ \t]*Recording Date:[ \t]*(.+?)[ \t]*$\n?", re.MULTILINE)


def _parse_recording_date(raw: str) -> str | None:
    """DD.MM.YYYY (./-/пробел как разделитель) -> ISO YYYY-MM-DD, иначе None."""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning(f"Unrecognized recording date {raw!r}; ignoring")
    return None


@logger.catch
def validate_template(text: str) -> dict[str, str] | None:
    """
    Validation of a text template and information extraction.

    Arguments:
    text (str): A text block.

    Is returning:
    Optional[dictation]: Information from the text database in the form of a dictionary.
    It does not arouse anyone's suspicions in connection with the flexibility of validation.

    Example:
    >>> template = "Number: 1\nTitle: Example header\nComment: Example comment"
    >>> validate_template(template)
    {'number': '1', 'title': '1. Example of a header', 'comment': 'Example of a comment'}
    """
    # Дату записи парсим отдельно и вырезаем строку до основного regex —
    # так поле остаётся опциональным и не усложняет и без того капризный шаблон.
    recording_date = None
    date_match = _RECORDING_DATE_RE.search(text)
    if date_match:
        recording_date = _parse_recording_date(date_match.group(1))
        text = text[: date_match.start()] + text[date_match.end() :]

    headers = ["number", "title", "comment"]
    if "chapters" in text.lower():
        reg = r"(?:<pre.*?>)?Number: (\d+)\nTitle: (.*?)\nComment: (.*?)\nTags: (.*?)\nChapters: \|\n((?:(?!<\/pre>).)*)(?:<\/pre>)?$"
        headers.extend(["tags", "chapters"])
    else:
        reg = r"(?:<pre.*?>)?Number: (\d+)\nTitle: (.*?)\nComment: ((?:(?!<\/pre>).)*)(?:<\/pre>)?$"

    match = re.search(reg, text, re.DOTALL)
    if not match or len(match.groups()) != len(headers):
        return None

    res = {header: match.group(i + 1).strip() for i, header in enumerate(headers)}
    res["title"] = f"{res['number']}. {res['title']}"

    if "chapters" in res:
        res["chapters"] = [
            [part.strip() for part in re.split(r"-|—", line, maxsplit=1)]
            for line in res["chapters"].splitlines()
            if line.strip()
        ]

    if "tags" in res:
        res["tags"] = list({tag.strip() for tag in re.split(r",\s*|,\s*|\s*,\s*", res["tags"])})

    if recording_date:
        res["recording_date"] = recording_date

    return res


@logger.catch
def validate_path(path: str, encoding="UTF-8") -> None:
    path_obj = Path(path)
    # Создаем все отсутствующие директории, если их нет
    if not path_obj.parent.exists():
        path_obj.parent.mkdir(parents=True, exist_ok=True)
    # Если файл уже существует, ничего не делаем
    if path_obj.exists():
        return
    # Иначе создаем пустой файл с указанной кодировкой
    path_obj.write_text("", encoding=encoding)
