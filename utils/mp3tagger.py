import os
import eyed3
from loguru import logger
from eyed3.id3 import UTF_16_ENCODING
from datetime import datetime
from config import COVER_RZ_PATH, COVER_PS_PATH, PODCAST


@logger.catch
def audiotag_RZ(**info):
    musician = "Разговорный жанр"
    name = info["name"]
    audiofile = eyed3.load(PODCAST)
    if audiofile.tag == None:
        audiofile.initTag((2, 4, 0))
    else:
        audiofile.tag.clear()
    audiofile.tag.artist = musician
    audiofile.tag.album = musician
    audiofile.tag.album_artist = musician
    audiofile.tag.title = name
    audiofile.tag.original_release_date = datetime.now().strftime("%Y-%m-%d")
    with open(COVER_RZ_PATH, "rb") as f:
        audiofile.tag.images.set(3, f.read(), "image/jpg", u"PodBOX")
    if info["text"] != " ":
        audiofile.tag.comments.set(info["text"])
        audiofile.tag.lyrics.set(info["text"])
    
    audiofile.tag.album_type = "single"
    audiofile.tag.artist_origin = eyed3.core.ArtistOrigin("Voronezh", "Voronezh region", "Russian Federation")
    audiofile.tag.artist_url = "https://podbox.ru/"
    audiofile.tag.commercial_url = "https://podbox.ru/donate/"
    audiofile.tag.payment_url = "https://podbox.ru/donate/"
    audiofile.tag.user_url_frames.set("https://podbox.ru/")
    audiofile.tag.copyright = musician
    audiofile.tag.publisher = musician
    audiofile.tag.genre = 186
    audiofile.tag.release_date = datetime.now().strftime("%Y-%m-%d")
    audiofile.tag.recording_date = datetime.now().strftime("%Y-%m-%d")
    info["chapters"].insert(0, "00:00:00 - Заставка")
    for i in range(len(info["chapters"])-1):
        begin = info["chapters"][i].split(" - ")
        end = info["chapters"][i+1].split(" - ")
        time1 = list(map(int, begin[0].split(":")))
        time2 = list(map(int, end[0].split(":")))
        added_chapter = audiofile.tag.chapters.set(bytes(begin[1], encoding='cp866'), (((time1[0] * 60 + time1[1]) * 60 + time1[2])*1000, ((time2[0] * 60 + time2[1]) * 60 + time2[2])*1000-1))
        added_chapter.encoding = UTF_16_ENCODING
        added_chapter.title = begin[1]

    begin = info["chapters"][-1].split(" - ")
    time1 = list(map(int, begin[0].split(":")))
    added_chapter = audiofile.tag.chapters.set(bytes(begin[1], encoding='cp866'), (((time1[0] * 60 + time1[1]) * 60 + time1[2])*1000, audiofile.info.time_secs*1000-1))
    added_chapter.encoding = UTF_16_ENCODING
    added_chapter.title = begin[1]
    audiofile.tag.save()


@logger.catch
def audiotag_PS(**info):
    musician = "Разговорный жанр"
    name = info["name"]
    audiofile = eyed3.load(PODCAST)
    if audiofile.tag == None:
        audiofile.initTag((2, 4, 0))
    else:
        audiofile.tag.clear()
    audiofile.tag.artist = musician
    audiofile.tag.album = musician
    audiofile.tag.album_artist = musician
    audiofile.tag.title = name
    audiofile.tag.original_release_date = datetime.now().strftime("%Y-%m-%d")
    with open(COVER_PS_PATH, "rb") as f:
        audiofile.tag.images.set(3, f.read(), "image/jpg", u"PodBOX")
    if info["text"] != " ":
        audiofile.tag.comments.set(info["text"])
        audiofile.tag.lyrics.set(info["text"])
    audiofile.tag.album_type = "single"
    audiofile.tag.artist_origin = eyed3.core.ArtistOrigin("Voronezh", "Voronezh region", "Russian Federation")
    audiofile.tag.artist_url = "https://podbox.ru/"
    audiofile.tag.commercial_url = "https://podbox.ru/donate/"
    audiofile.tag.payment_url = "https://podbox.ru/donate/"
    audiofile.tag.user_url_frames.set("https://podbox.ru/")
    audiofile.tag.copyright = musician
    audiofile.tag.publisher = musician
    audiofile.tag.genre = 186
    audiofile.tag.release_date = datetime.now().strftime("%Y-%m-%d")
    audiofile.tag.recording_date = datetime.now().strftime("%Y-%m-%d")
    audiofile.tag.save()