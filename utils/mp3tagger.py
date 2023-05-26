import eyed3
from loguru import logger
from eyed3.id3 import UTF_16_ENCODING
from datetime import datetime
from config import COVER_RZ_PATH, COVER_PS_PATH, PODCAST_PATH

@logger.catch
def audiotag(info):
    #TODO
    pass


@logger.catch
def audiotag_RZ(info):
    musician = "Разговорный жанр"
    title = info["title"]
    audiofile = eyed3.load(PODCAST_PATH)
    if audiofile.tag == None:
        audiofile.initTag((2, 4, 0))
    else:
        audiofile.tag.clear()
    audiofile.tag.artist = musician
    audiofile.tag.album = musician
    audiofile.tag.title = f'{info["number"]}. {title}'
    audiofile.tag.original_release_date = datetime.now().year
    #TODO CHECK THIS
    with open(COVER_RZ_PATH, "rb") as f:
        audiofile.tag.images.set(3, f.read(), "image/jpg", u"")
    comment = info["comment"]
    if comment != " ":
        audiofile.tag.comments.set(comment)
        audiofile.tag.lyrics.set(comment)
    
    audiofile.tag.album_type = "single"
    audiofile.tag.artist_origin = eyed3.core.ArtistOrigin("Voronezh", "Voronezh region", "Russian Federation")
    audiofile.tag.artist_url = "https://podbox.ru/"
    audiofile.tag.commercial_url = "https://podbox.ru/donate/"
    audiofile.tag.payment_url = "https://podbox.ru/donate/"
    audiofile.tag.user_url_frames.set("https://podbox.ru/")
    audiofile.tag.copyright = musician
    audiofile.tag.publisher = musician
    audiofile.tag.genre = 186 # Podcast
    audiofile.tag.release_date = datetime.now().year
    audiofile.tag.recording_date = datetime.now().year
    info["chapters"].insert(0, "00:00:00 - Заставка")
    for i in range(len(info["chapters"])-1):
        begin = info["chapters"][i]
        end = info["chapters"][i+1]
        time1 = list(map(int, begin[0].split(":"))) #TODO REFACTOR THIS
        time2 = list(map(int, end[0].split(":"))) #TODO REFACTOR THIS
        added_chapter = audiofile.tag.chapters.set(bytes(begin[1], encoding='cp866'), (((time1[0] * 60 + time1[1]) * 60 + time1[2])*1000, ((time2[0] * 60 + time2[1]) * 60 + time2[2])*1000-1))
        added_chapter.encoding = UTF_16_ENCODING
        added_chapter.title = begin[1]

    begin = info["chapters"][-1]
    time1 = list(map(int, begin[0].split(":"))) #TODO REFACTOR THIS
    added_chapter = audiofile.tag.chapters.set(bytes(begin[1], encoding='cp866'), (((time1[0] * 60 + time1[1]) * 60 + time1[2])*1000, audiofile.info.time_secs*1000-1))
    added_chapter.encoding = UTF_16_ENCODING
    added_chapter.title = begin[1]
    audiofile.tag.save()


@logger.catch
def audiotag_PS(info):
    musician = "Разговорный жанр"
    title = info["title"]
    audiofile = eyed3.load(PODCAST_PATH)
    if audiofile.tag == None:
        audiofile.initTag((2, 4, 0))
    else:
        audiofile.tag.clear()
    audiofile.tag.artist = musician
    audiofile.tag.album = musician
    audiofile.tag.title = f'{info["number"]}. {title}'
    audiofile.tag.original_release_date = datetime.now().year
    with open(COVER_PS_PATH, "rb") as f:
        audiofile.tag.images.set(3, f.read(), "image/jpg", u"")

    comment = info["comment"]
    if info["comment"] != " ":
        audiofile.tag.comments.set(comment)
        audiofile.tag.lyrics.set(comment)
    audiofile.tag.album_type = "single"
    audiofile.tag.artist_origin = eyed3.core.ArtistOrigin("Voronezh", "Voronezh region", "Russian Federation")
    audiofile.tag.artist_url = "https://podbox.ru/"
    audiofile.tag.commercial_url = "https://podbox.ru/donate/"
    audiofile.tag.payment_url = "https://podbox.ru/donate/"
    audiofile.tag.user_url_frames.set("https://podbox.ru/")
    audiofile.tag.copyright = musician
    audiofile.tag.publisher = musician
    audiofile.tag.genre = 186 # Podcast
    audiofile.tag.release_date = datetime.now().year
    audiofile.tag.recording_date = datetime.now().year
    audiofile.tag.save()