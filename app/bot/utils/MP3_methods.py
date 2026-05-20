from datetime import datetime

import eyed3
from eyed3 import AudioFile
from eyed3.id3 import ID3_V2_4, UTF_16_ENCODING
from loguru import logger

from config import (
    COVER_PS_PATH,
    COVER_RZ_PATH,
    PODCAST_CITY,
    PODCAST_COUNTRY,
    PODCAST_DISTRICT,
    PODCAST_GENRE,
    PODCAST_LINK,
    PODCAST_NAME,
    PODCAST_PATH,
    SUPPORT_LINK,
    TIMEZONE,
)


@logger.catch
def time_to_milliseconds(time_str: str) -> int | None:
    try:
        hours, minutes, seconds = map(int, time_str.split(":"))

        # Проверка допустимых значений времени
        if not (0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
            logger.error(f"Invalid time value: {time_str}")
            return None

        return (((hours * 60) + minutes) * 60 + seconds) * 1000
    except (ValueError, AttributeError) as e:
        logger.error(f"Invalid time format: {time_str} - {e}")
        return None


@logger.catch
def set_chapters(audio_file: AudioFile, chapters: list[tuple[str, str]]) -> None:
    # Если тег отсутствует, инициализируем его
    if audio_file.tag is None:
        audio_file.initTag(ID3_V2_4)

    for i, (startTime, title) in enumerate(chapters):
        timeStart = time_to_milliseconds(startTime)
        timeEnd = time_to_milliseconds(chapters[i + 1][0]) if i < len(chapters) - 1 else int(audio_file.info.time_secs)
        addedChapter = audio_file.tag.chapters.set(
            bytes(f"CHAP{i + 1}", encoding="cp866"),
            (timeStart, timeEnd - 1),
        )
        addedChapter.encoding = UTF_16_ENCODING
        addedChapter.title = title


@logger.catch
def audio_tag(info: dict, type: str) -> None:
    year = datetime.now(TIMEZONE).year
    audio_file = eyed3.load(PODCAST_PATH)

    if audio_file is None:
        logger.error("Audio file not found or could not be loaded")
        return

    if audio_file.tag is None:
        logger.info("Initializing new tag")
        audio_file.initTag(ID3_V2_4)
    else:
        logger.info("Clearing existing tag")  # Добавляем отладку
        audio_file.tag.clear()

    audio_file.tag.artist = PODCAST_NAME
    audio_file.tag.album = PODCAST_NAME
    audio_file.tag.title = info["title"]
    audio_file.tag.original_release_date = year

    COVER_PATH = COVER_RZ_PATH if type == "main" else COVER_PS_PATH
    with open(COVER_PATH, "rb") as f:
        audio_file.tag.images.set(3, f.read(), "image/jpg", "")

    comment = info["comment"]
    if comment != " ":
        audio_file.tag.comments.set(comment)
        audio_file.tag.lyrics.set(comment)

    audio_file.tag.album_type = "single"
    audio_file.tag.artist_origin = eyed3.core.ArtistOrigin(PODCAST_CITY, PODCAST_DISTRICT, PODCAST_COUNTRY)
    audio_file.tag.artist_url = PODCAST_LINK
    audio_file.tag.commercial_url = SUPPORT_LINK
    audio_file.tag.payment_url = SUPPORT_LINK
    audio_file.tag.user_url_frames.set(PODCAST_LINK)
    audio_file.tag.copyright = PODCAST_NAME
    audio_file.tag.publisher = PODCAST_NAME
    audio_file.tag.genre = PODCAST_GENRE
    audio_file.tag.release_date = year
    audio_file.tag.recording_date = year

    if type == "main":
        set_chapters(audio_file, info.get("chapters", []))

    audio_file.tag.save()
