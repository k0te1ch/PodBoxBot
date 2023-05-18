import os
import eyed3
from eyed3.id3 import UTF_16_ENCODING
from datetime import datetime

def audiotag(**info):
    #TODO PHOTOPATH
    #TODO MUSICPATH
    PHOTOSPATH = "src/files/cover.jpg"
    MUSICPATH = "src/files/podcast.mp3"
    musician = "Разговорный жанр"
    name = info["name"]
    audiofile = eyed3.load(f"{MUSICPATH}")
    if audiofile.tag == None:
        audiofile.initTag((2, 4, 0))
    else:
        audiofile.tag.clear()
    audiofile.tag.artist = musician
    audiofile.tag.album = musician
    audiofile.tag.album_artist = musician
    audiofile.tag.title = name
    audiofile.tag.original_release_date = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(f"{PHOTOSPATH}"):
        with open(f"{PHOTOSPATH}", "rb") as f:
            audiofile.tag.images.set(3, f.read(), "image/jpg", u"Discription")
    if info["text"] != " ":
        audiofile.tag.comments.set(info["text"])
    
    audiofile.tag.album_type = "single"
    audiofile.tag.artist_origin = eyed3.core.ArtistOrigin("Voronezh", "Voronezh region", "Russian Federation")
    audiofile.tag.artist_url = "https://podbox.ru/"
    audiofile.tag.commercial_url = "boosty"
    audiofile.tag.payment_url = "boosty"
    audiofile.tag.user_url_frames.set("https://podbox.ru/")
    audiofile.tag.copyright = musician
    audiofile.tag.publisher = musician
    audiofile.tag.disc_num = (1, 1)
    audiofile.tag.track_num = (info["number"], info["number"])
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
