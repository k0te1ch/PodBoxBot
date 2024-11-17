from pathlib import Path
import re
from typing import Optional, Dict

from loguru import logger

from config import SUPPORT_LINK


@logger.catch
def validate_template(text: str) -> Optional[Dict[str, str]]:
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
    res["title"] = f'{res["number"]}. {res["title"]}'

    if "chapters" in res:
        res["chapters"] = [
            [part.strip() for part in re.split(r"-|—", line, maxsplit=1)]
            for line in res["chapters"].splitlines()
            if line.strip()
        ]

    if "tags" in res:
        res["tags"] = list(set(tag.strip() for tag in re.split(r",\s*|,\s*|\s*,\s*", res["tags"])))

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


@logger.catch
def generate_podcast_text(info: dict) -> str:
    """
    Генерирует текст для поста подкаста на основе переданных данных.

    Args:
        info (dict): Словарь с информацией о подкасте, включающий:
                     - number (str): номер эпизода
                     - title (str): название эпизода
                     - summary (str): описание эпизода
                     - chapters (list of tuples): главы с временем и названием (в формате [("00:00:07", "Вступление"), ...])
                     - support_link (str): ссылка на поддержку

    Returns:
        str: Сформированный текст подкаста.
    """

    episode_number = info["number"]
    title = info["title"]
    summary = info["comment"]
    chapters = info["chapters"]

    # Форматирование таймлайна
    formatted_chapters = "\n".join(f"{time} — {chapter}" for time, chapter in chapters)

    # Создание текста
    podcast_text = (
        f"<b>{title}</b>\n\n"
        f"<i>Описание:</i>\n"
        f"{summary}\n\n"
        f"<i>Таймлайн:</i>\n"
        f"{formatted_chapters}\n\n"
        f"Всё это вы услышите в {episode_number}-м эпизоде подкаста «Разговорный жанр».\n\n"
        f'<i><b><a href="{SUPPORT_LINK}">💰 Поддержать подкаст</a></b></i>'
    )

    return podcast_text
