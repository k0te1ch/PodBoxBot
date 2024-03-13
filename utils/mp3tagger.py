from typing import List, Tuple
import eyed3
from eyed3 import AudioFile
from loguru import logger
from eyed3.id3 import UTF_16_ENCODING
from datetime import datetime
from eyed3.id3.tag import Tag
from config import COVER_RZ_PATH, COVER_PS_PATH, PODCAST_PATH, TIMEZONE, PODCAST_GENRE


@logger.catch
def time_to_milliseconds(time_str: str) -> int:
    hours, minutes, seconds = map(int, time_str.split(":"))
    return ((hours * 60) + minutes) * 60 + seconds


@logger.catch
def set_chapters(audioFile: AudioFile, chapters: List[Tuple[str, str]]) -> None:
    if len(chapters) == 0:
        return
    tag: Tag = audioFile.tag
    for i, (startTime, title) in enumerate(chapters):
        timeStart = time_to_milliseconds(startTime)
        timeEnd = (
            time_to_milliseconds(chapters[i + 1][0])
            if i < len(chapters) - 1
            else int(audioFile.info.time_secs)
        )
        addedChapter = tag.chapters.set(
            bytes(f"CHAP{i+1}", encoding="cp866"),
            (timeStart, timeEnd - 1),
        )
        addedChapter.encoding = UTF_16_ENCODING
        addedChapter.title = title


@logger.catch
def audioTag(info: dict, type: str) -> None:
    year = datetime.now(TIMEZONE).year
    musician = "Разговорный жанр"  # TODO to env
    audioFile = eyed3.load(PODCAST_PATH)
    if audioFile is None:
        return

    if audioFile.tag is None:
        audioFile.initTag((2, 4, 0))
    else:
        audioFile.tag.clear()

    audioFile.tag.artist = musician
    audioFile.tag.album = musician
    audioFile.tag.title = info["title"]
    audioFile.tag.original_release_date = datetime.now(TIMEZONE).year
    COVER_PATH = COVER_RZ_PATH if type == "main" else COVER_PS_PATH
    with open(COVER_PATH, "rb") as f:
        audioFile.tag.images.set(3, f.read(), "image/jpg", "")
    comment = info["comment"]
    if comment != " ":
        audioFile.tag.comments.set(comment)
        audioFile.tag.lyrics.set(comment)

    audioFile.tag.album_type = "single"
    audioFile.tag.artist_origin = eyed3.core.ArtistOrigin(
        "Voronezh", "Voronezh region", "Russian Federation"
    )  # TODO to settings
    audioFile.tag.artist_url = "https://podbox.ru/"  # TODO to settings
    audioFile.tag.commercial_url = "https://podbox.ru/donate/"  # TODO to settings
    audioFile.tag.payment_url = "https://podbox.ru/donate/"  # TODO to settings
    audioFile.tag.user_url_frames.set("https://podbox.ru/")  # TODO to settings
    audioFile.tag.copyright = musician
    audioFile.tag.publisher = musician
    audioFile.tag.genre = PODCAST_GENRE
    audioFile.tag.release_date = year
    audioFile.tag.recording_date = year
    if type == "main":
        set_chapters(audioFile, info.get("chapters", []))
    audioFile.tag.save()
