"""Фото и тяжёлые вложения у пунктов списка."""

from unittest.mock import MagicMock

import pytest
from aiogram.enums import ChatType

from handlers import topics_handler as th
from services.topics import Author, Item, Kind, Source
from services.topics.listing import list_pages
from services.topics.media import attachments, message_link
from services.topics.runtime import topic_list


def _photo(file_id: str):
    return [MagicMock(file_id=f"{file_id}-small"), MagicMock(file_id=file_id)]


def _chat(chat_id: int, username: str | None, kind=ChatType.SUPERGROUP):
    chat = MagicMock()
    chat.id, chat.username, chat.type = chat_id, username, kind
    return chat


def _message(chat, message_id=5, **fields):
    msg = MagicMock()
    msg.chat, msg.message_id = chat, message_id
    for name in ("photo", "video", "animation", "document", "video_note", "audio", "voice"):
        setattr(msg, name, fields.get(name))
    return msg


@pytest.mark.parametrize(
    ("chat", "link"),
    [
        (_chat(-1001234567890, "podcast_chat"), "https://t.me/podcast_chat/5"),
        (_chat(-1001234567890, None), "https://t.me/c/1234567890/5"),
        (_chat(-1001234567890, "bad name!"), "https://t.me/c/1234567890/5"),
        (_chat(-100123, None, ChatType.CHANNEL), "https://t.me/c/123/5"),
        (_chat(-4567, None, ChatType.GROUP), None),
        (_chat(7, None, ChatType.PRIVATE), None),
    ],
)
def test_message_link_uses_only_public_chat_data(chat, link):
    assert message_link(_message(chat)) == link


def test_photo_is_the_biggest_size_and_video_becomes_a_link():
    chat = _chat(-1001234567890, "podcast_chat")
    photo = _message(chat, photo=_photo("big"))
    video = _message(chat, message_id=9, video=MagicMock())

    assert attachments(photo) == ("big", None)
    assert attachments(photo, video) == ("big", "https://t.me/podcast_chat/9")
    assert attachments(None, _message(chat)) == (None, None)


@pytest.mark.asyncio
async def test_hashtag_caption_pins_the_photo_to_the_item(fake_redis, bot, group_message):
    msg = group_message("#вопрос что на этом фото?")
    msg.photo = _photo("AgACbig")

    await th.collect_from_chat(msg, bot, Kind.QUESTION)

    [item] = await topic_list().repository.items()
    assert (item.photo, item.media_link) == ("AgACbig", None)


@pytest.mark.asyncio
async def test_hashtag_reply_to_a_photo_takes_that_photo(fake_redis, bot, group_message):
    original = group_message("", message_id=90)
    original.photo = _photo("AgACreplied")
    msg = group_message("#тема разберём это фото", reply_to=original)

    await th.collect_from_chat(msg, bot, Kind.TOPIC)

    [item] = await topic_list().repository.items()
    assert item.photo == "AgACreplied"


@pytest.mark.asyncio
async def test_video_is_not_embedded_but_linked(fake_redis, bot, group_message):
    msg = group_message("#тема смотрите ролик про выпуск")
    msg.video = MagicMock()

    await th.collect_from_chat(msg, bot, Kind.TOPIC)

    [item] = await topic_list().repository.items()
    assert (item.photo, item.media_link) == (None, "https://t.me/test_group/100")


def _item(**fields) -> Item:
    return Item(
        text="тема", kind=Kind.TOPIC, author=Author(name="@a", user_id=7), source=Source.HASHTAG, id=3, **fields
    )


def test_list_embeds_the_photo_and_links_the_video():
    [page] = list_pages([_item(photo="AgAC"), _item(media_link="https://t.me/test_group/100")])

    assert '<img src="tg://photo?id=i3">' in page.html
    assert [(m.id, m.media.media) for m in page.media] == [("i3", "AgAC")]
    assert '<a href="https://t.me/test_group/100">вложение</a>' in page.html
    assert '(<a href="https://t.me/test_group/100">вложение</a>)' in page.text


def test_plain_list_has_no_media():
    [page] = list_pages([_item()])

    assert page.media == []
    assert "<img" not in page.html
