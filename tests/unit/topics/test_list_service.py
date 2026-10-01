"""Хранилище и сервис списка: приём, отказы, удаление и возврат, бан."""

import pytest

from services.topics import Author, Item, Kind, Refusal, Source
from services.topics.runtime import topic_list


def _item(text="как выбирать гостей", *, kind=Kind.TOPIC, user_id=7, message_id=None) -> Item:
    return Item(
        text=text,
        kind=kind,
        author=Author(name="@listener", user_id=user_id),
        source=Source.HASHTAG,
        chat_id=-100 if message_id else None,
        message_id=message_id,
    )


@pytest.mark.asyncio
async def test_items_keep_kind_and_come_oldest_first(fake_redis):
    service = topic_list()
    await service.add(_item("  почему   небо голубое? ", kind=Kind.QUESTION))
    await service.add(_item("как съездили в отпуск"))

    items = await service.repository.items()

    assert [(item.kind, item.text) for item in items] == [
        (Kind.QUESTION, "почему небо голубое?"),
        (Kind.TOPIC, "как съездили в отпуск"),
    ]
    assert await service.repository.count() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("text", "refusal"), [("ой", Refusal.TOO_SHORT), ("я" * 51, Refusal.TOO_LONG)])
async def test_length_is_checked(fake_redis, text, refusal):
    result = await topic_list().add(_item(text))

    assert (result.item, result.refusal) == (None, refusal)


@pytest.mark.asyncio
async def test_limit_and_ban_stop_a_listener_but_not_an_admin(fake_redis):
    service = topic_list()
    for index in range(2):
        assert (await service.add(_item(f"идея номер {index}"))).item is not None

    assert (await service.add(_item("третья идея за сутки"))).refusal is Refusal.LIMIT
    assert (await service.add(_item("от админа", user_id=7), trusted=True)).item is not None

    await service.repository.ban(8, "@spammer")
    assert (await service.add(_item("а можно мне?", user_id=8))).refusal is Refusal.BANNED
    assert await service.repository.banned() == {8: "@spammer"}
    await service.repository.unban(8)
    assert await service.repository.banned() == {}
    assert (await service.add(_item("теперь можно", user_id=8))).item is not None


@pytest.mark.asyncio
async def test_admin_text_may_be_short_but_not_empty(fake_redis):
    service = topic_list()

    assert (await service.add(_item("Юг"), trusted=True)).item is not None
    assert (await service.add(_item("   "), trusted=True)).refusal is Refusal.TOO_SHORT


@pytest.mark.asyncio
async def test_same_chat_message_is_added_once(fake_redis):
    service = topic_list()
    await service.add(_item(message_id=5))

    again = await service.add(_item(message_id=5))
    by_admin = await service.add(_item(message_id=5), trusted=True)

    assert again.refusal is Refusal.DUPLICATE
    assert by_admin.refusal is Refusal.DUPLICATE
    assert await service.repository.count() == 1


@pytest.mark.asyncio
async def test_admin_can_take_a_message_the_bot_refused(fake_redis):
    service = topic_list()
    for index in range(2):
        await service.add(_item(f"идея номер {index}"))
    refused = await service.add(_item("третья идея за сутки", message_id=5))
    assert refused.refusal is Refusal.LIMIT

    # Повторная доставка апдейта молча отсекается, а админ взять сообщение может.
    assert (await service.add(_item("третья идея за сутки", message_id=5))).refusal is Refusal.DUPLICATE
    assert (await service.add(_item("третья идея за сутки", message_id=5), trusted=True)).item is not None
    assert (await service.add(_item("третья идея за сутки", message_id=5), trusted=True)).refusal is Refusal.DUPLICATE


@pytest.mark.asyncio
async def test_removed_items_leave_the_list_and_can_be_restored(fake_redis):
    service = topic_list()
    first = (await service.add(_item("первая тема"))).item
    second = (await service.add(_item("вторая тема"))).item

    removed = await service.remove([first.id, 999], moderator_id=1)
    assert [item.id for item in removed] == [first.id]
    assert [item.id for item in await service.repository.items()] == [second.id]
    # Второй раз удалять нечего.
    assert await service.remove([first.id]) == []

    restored = await service.restore([first.id, second.id])
    assert [item.id for item in restored] == [first.id]
    assert [item.id for item in await service.repository.items()] == [first.id, second.id]


@pytest.mark.asyncio
async def test_removing_does_not_reset_the_author_limit(fake_redis):
    service = topic_list()
    items = [(await service.add(_item(f"идея номер {index}"))).item for index in range(2)]
    await service.remove([item.id for item in items])

    assert (await service.add(_item("ещё одна идея"))).refusal is Refusal.LIMIT


@pytest.mark.asyncio
async def test_anonymous_author_has_no_limit(fake_redis):
    service = topic_list()
    for index in range(4):
        result = await service.add(_item(f"от имени канала {index}", user_id=None))
        assert result.item is not None and result.item.author.user_id is None
