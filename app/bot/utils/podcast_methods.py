from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger

from config import SUPPORT_LINK, TIMEZONE


class EpisodeType(Enum):
    MAIN = "main"
    POSTSHOW = "postshow"


# Константы
EPISODE_PREFIXES = {EpisodeType.MAIN: "rz", EpisodeType.POSTSHOW: "postshow"}
DATE_FORMAT = "%d%m%Y"
FILE_EXTENSION = ".mp3"
EPISODE_NUMBER_LENGTH = 4


@logger.catch
def generate_podcast_text(info: dict[str, Any]) -> str | None:
    """
    Генерирует текст для поста подкаста на основе переданных данных.

    Args:
        info (dict): Словарь с информацией о подкасте, включающий:
                     - number (str): номер эпизода
                     - title (str): название эпизода
                     - comment (str): описание эпизода
                     - chapters (list[tuple[str, str]]): главы с временем и названием (например, [("00:00:07", "Вступление"), ...])
                     - support_link (str, optional): ссылка на поддержку (необязательно, иначе используется SUPPORT_LINK)

    Returns:
        Optional[str]: Сформированный текст подкаста или None при ошибке.
    """
    try:
        # Валидация ключей
        required_keys = ["number", "title", "comment", "chapters"]
        if not all(key in info for key in required_keys):
            missing = [key for key in required_keys if key not in info]
            logger.error(f"Отсутствуют обязательные поля: {', '.join(missing)}")
            return None

        # Извлечение данных
        episode_number = info.get("number")
        title = info.get("title")
        summary = info.get("comment")
        chapters = info.get("chapters")
        support_link = info.get("support_link", SUPPORT_LINK)

        # Проверка типов данных
        if not isinstance(chapters, list) or not all(isinstance(ch, list) and len(ch) == 2 for ch in chapters):
            logger.error("Некорректный формат глав. Ожидается список списков (время, название)")
            return None

        # Форматирование таймлайна
        formatted_chapters = "\n".join(f"{time} — {chapter}" for time, chapter in chapters) if chapters else "Нет глав"

        # Создание текста
        podcast_text = (
            f"<b>{title}</b>\n\n"
            f"<i>Описание:</i>\n{summary}\n\n"
            f"<i>Таймлайн:</i>\n{formatted_chapters}\n\n"
            f"Всё это вы услышите в {episode_number}-м эпизоде подкаста «Разговорный жанр».\n\n"
            f'<i><b><a href="{support_link}">🍩 Поддержать подкаст</a></b></i>'
        )
        return podcast_text

    except Exception as e:
        logger.exception(f"Ошибка при генерации текста подкаста: {e}")
        return None


@logger.catch
def generate_file_name(number: str, type_episode: str, extension: str = FILE_EXTENSION) -> str:
    """
    Генерирует имя файла для подкаста.

    Args:
        number (str): Номер эпизода
        type_episode (str): Тип эпизода ('main' или 'postshow')
        extension (str, optional): Расширение файла. По умолчанию '.mp3'

    Returns:
        str: Имя файла в формате '{номер}_{префикс}_{дата}{расширение}'

    Raises:
        ValueError: Если type_episode имеет недопустимое значение или номер некорректный
        TypeError: Если number не является строкой
    """
    # Проверка типа и валидация номера эпизода
    if not isinstance(number, str):
        raise TypeError("number должен быть строкой")

    if not number.strip():
        raise ValueError("Номер эпизода не может быть пустым")

    if not number.isdigit():
        raise ValueError("Номер эпизода должен содержать только цифры")

    # Преобразование строкового типа в enum
    try:
        episode_type = EpisodeType(type_episode)
    except ValueError as err:
        raise ValueError(f"type_episode должен быть одним из: {[e.value for e in EpisodeType]}") from err

    # Нормализация расширения файла
    if not extension.startswith("."):
        extension = f".{extension}"

    # Формирование имени файла
    current_date = datetime.now(TIMEZONE).strftime(DATE_FORMAT)
    prefix = EPISODE_PREFIXES[episode_type]

    return Path(f"{number.zfill(EPISODE_NUMBER_LENGTH)}_{prefix}_{current_date}{extension}").name
