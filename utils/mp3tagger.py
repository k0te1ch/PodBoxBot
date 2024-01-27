from typing import List, Tuple
import eyed3
from loguru import logger
from eyed3.id3 import UTF_16_ENCODING
from datetime import datetime, timedelta, timezone
from eyed3.id3.tag import Tag
from config import COVER_RZ_PATH, COVER_PS_PATH, PODCAST_PATH

# TODO timezone to settings
timeZone = timezone(timedelta(hours=3))
PODCAST_GENRE = 186  # TODO TO CONFIG


def time_to_milliseconds(time_str: str) -> int:
    hours, minutes, seconds = map(int, time_str.split(":"))
    return ((hours * 60) + minutes) * 60 + seconds


def set_chapters(tag: Tag, chapters: List[Tuple[str, str]]) -> None:
    for i, (start_time, title) in enumerate(chapters):
        time_start = time_to_milliseconds(start_time)
        time_end = (
            time_to_milliseconds(chapters[i + 1][0])
            if i < len(chapters) - 1
            else tag.frame_set("TLEN").text[0]
        )
        added_chapter = tag.chapters.set(
            bytes(f"CHAP{i+1}", encoding="cp866"),
            (time_start, time_end - 1),
        )
        added_chapter.encoding = UTF_16_ENCODING
        added_chapter.title = title


@logger.catch
def audiotag(info: dict, type: str) -> None:
    musician = "Разговорный жанр"  # TODO to env
    with eyed3.load(PODCAST_PATH) as audiofile:
        if audiofile is None:
            return

        if audiofile.tag == None:
            audiofile.initTag((2, 4, 0))
        else:
            audiofile.tag.clear()
        tags = ("artist", "album", "title", "title", "original_release_date")

        # if all(i in d for i in tags)
        audiofile.tag.artist = musician
        audiofile.tag.album = musician
        audiofile.tag.title = info["title"]
        audiofile.tag.original_release_date = datetime.now(timeZone).year
        COVER_PATH = COVER_RZ_PATH if type == "main" else COVER_PS_PATH
        with open(COVER_PATH, "rb") as f:
            audiofile.tag.images.set(3, f.read(), "image/jpg", "")
        comment = info["comment"]
        if comment != " ":
            audiofile.tag.comments.set(comment)
            audiofile.tag.lyrics.set(comment)

        audiofile.tag.album_type = "single"
        audiofile.tag.artist_origin = eyed3.core.ArtistOrigin(
            "Voronezh", "Voronezh region", "Russian Federation"
        )  # TODO to settings
        audiofile.tag.artist_url = "https://podbox.ru/"  # TODO to settings
        audiofile.tag.commercial_url = "https://podbox.ru/donate/"  # TODO to settings
        audiofile.tag.payment_url = "https://podbox.ru/donate/"  # TODO to settings
        audiofile.tag.user_url_frames.set("https://podbox.ru/")  # TODO to settings
        audiofile.tag.copyright = musician
        audiofile.tag.publisher = musician
        audiofile.tag.genre = PODCAST_GENRE
        audiofile.tag.release_date = datetime.now(timeZone).year
        audiofile.tag.recording_date = datetime.now(timeZone).year
        if type == "main":
            set_chapters(audiofile.tag, info.get("chapters", []))
        audiofile.tag.save()
