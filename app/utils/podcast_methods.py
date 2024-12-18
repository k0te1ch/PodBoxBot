from datetime import datetime
from loguru import logger

from config import SUPPORT_LINK, TIMEZONE

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


def generate_file_name(number: str, type_episode: str) -> str:
    prefix = "rz" if type_episode == "main" else "postshow"

    return f'{number.zfill(4)}_{prefix}_{datetime.now(TIMEZONE).strftime("%d%m%Y")}.mp3'
