import eyed3
from loguru import logger
from eyed3.id3 import UTF_16_ENCODING
from datetime import datetime, timedelta, timezone
from config import COVER_RZ_PATH, COVER_PS_PATH, PODCAST_PATH
# TODO timezone to settings
timeZone = timezone(timedelta(hours=3))


@logger.catch
def audiotag(info: dict, type: str) -> None:
    musician = "Разговорный жанр"
    audiofile = eyed3.load(PODCAST_PATH)
    if audiofile == None:
        return
    if audiofile.tag == None:
        audiofile.initTag((2, 4, 0))
    else:
        audiofile.tag.clear()
    tags = ("artist", "album", "title", "title", "original_release_date")
    
    #if all(i in d for i in tags)
    audiofile.tag.artist = musician
    audiofile.tag.album = musician
    audiofile.tag.title = info["title"]
    audiofile.tag.original_release_date = datetime.now().year
    with open(COVER_RZ_PATH, "rb") as f:
        audiofile.tag.images.set(3, f.read(), "image/jpg", u"")
    comment = info["comment"]
    if comment != " ":
        audiofile.tag.comments.set(comment)
        audiofile.tag.lyrics.set(comment)

    audiofile.tag.album_type = "single"
    audiofile.tag.artist_origin = eyed3.core.ArtistOrigin(
        "Voronezh", "Voronezh region", "Russian Federation") # TODO to settings
    audiofile.tag.artist_url = "https://podbox.ru/" # TODO to settings
    audiofile.tag.commercial_url = "https://podbox.ru/donate/" # TODO to settings
    audiofile.tag.payment_url = "https://podbox.ru/donate/" # TODO to settings
    audiofile.tag.user_url_frames.set("https://podbox.ru/") # TODO to settings
    audiofile.tag.copyright = musician
    audiofile.tag.publisher = musician
    audiofile.tag.genre = 186  # Podcast
    audiofile.tag.release_date = datetime.now(timeZone).year
    audiofile.tag.recording_date = datetime.now(timeZone).year
    if type != "main":
        audiofile.tag.save()
        return
    for i in range(len(info["chapters"]) - 1):
        begin = info["chapters"][i]
        end = info["chapters"][i + 1]
        time1 = list(map(int, begin[0].split(":")))  #TODO REFACTOR THIS
        time2 = list(map(int, end[0].split(":")))  #TODO REFACTOR THIS
        added_chapter = audiofile.tag.chapters.set(
            bytes(f"CHAP{i+1}", encoding='cp866'),
            (((time1[0] * 60 + time1[1]) * 60 + time1[2]) * 1000,
             ((time2[0] * 60 + time2[1]) * 60 + time2[2]) * 1000 - 1))
        added_chapter.encoding = UTF_16_ENCODING
        added_chapter.title = begin[1]

    begin = info["chapters"][-1]
    time1 = list(map(int, begin[0].split(":")))  #TODO REFACTOR THIS
    added_chapter = audiofile.tag.chapters.set(
        bytes(f"CHAP{len(begin)}", encoding='cp866'),
        (((time1[0] * 60 + time1[1]) * 60 + time1[2]) * 1000,
         audiofile.info.time_secs * 1000 - 1))
    added_chapter.encoding = UTF_16_ENCODING
    added_chapter.title = begin[1]
    audiofile.tag.save()