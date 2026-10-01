"""Где лежит список тем и вопросов.

Хендлеры работают только с протоколом :class:`ListRepository`. Реализация,
:class:`SuggestListRepository`, держит пункты в очереди модуля ``suggest`` из
sagenza-tgbot-sdk (:class:`SuggestionBox` поверх ``RedisSuggestStore``): там
же лимит на автора и бан-лист.

Список один, статусов у пункта для ведущих нет. В очереди SDK их два:

* ``new``: пункт в списке;
* ``taken``: пункт убран из списка («обсудили»). Запись остаётся в Redis,
  поэтому удаление можно отменить, а лимит автора не обнуляется.

Своего в адаптере три вещи:

* ``<ns>:src:<chat>:<message>`` в Redis: какое сообщение чата уже стало
  пунктом (значение: id пункта, ``0`` пока сообщение отклонено). Telegram
  может доставить апдейт повторно, а у SDK отсечки по сообщению нет;
* ``<ns>:bans`` в Redis: имена забаненных авторов, чтобы показать их админу
  (SDK хранит только id);
* автор без id (пост от имени канала, анонимный админ) хранится с
  ``author_id=0`` и лимитом не ограничивается: считать его не по кому.
"""

from typing import Any, Protocol

from sagenza_tgbot_sdk.suggest import Suggestion, SuggestionBox, SuggestionStatus

from services.topics.models import Author, Item, Kind, Source

LIST_LIMIT = 500
# Метка сообщения нужна против повторной доставки апдейта и повторного
# добавления админом, дольше месяца её держать незачем.
ORIGIN_TTL_SECONDS = 30 * 24 * 3600
ANONYMOUS_AUTHOR_ID = 0
REFUSED_ORIGIN = "0"

IN_LIST = SuggestionStatus.NEW
REMOVED = SuggestionStatus.TAKEN


class ListRepository(Protocol):
    async def add(self, item: Item, *, check_limits: bool = True) -> Item | None:
        """Сохранить пункт и выдать ему id; ``None``, если это сообщение уже в списке.

        Отказ по лимиту или бану: :class:`SuggestionRejectedError` из SDK.
        """

    async def get(self, item_id: int) -> Item | None:
        """Пункт по id, даже если его уже убрали из списка."""

    async def items(self) -> list[Item]:
        """Пункты списка, старые сверху."""

    async def count(self) -> int: ...

    async def remove(self, item_id: int, moderator_id: int | None = None) -> Item | None:
        """Убрать пункт из списка; ``None``, если его там нет."""

    async def restore(self, item_id: int) -> Item | None:
        """Вернуть убранный пункт; ``None``, если возвращать нечего."""

    async def ban(self, user_id: int, name: str) -> None: ...

    async def unban(self, user_id: int) -> None: ...

    async def is_banned(self, user_id: int) -> bool: ...

    async def banned(self) -> dict[int, str]:
        """Забаненные авторы: id → имя."""


def _text(raw: str | bytes) -> str:
    return raw.decode() if isinstance(raw, bytes) else raw


def _kind(raw: str | None) -> Kind:
    try:
        return Kind(raw)
    except ValueError:
        return Kind.TOPIC


def _source(raw: str) -> Source:
    try:
        return Source(raw)
    except ValueError:
        return Source.FORM


def to_item(suggestion: Suggestion) -> Item:
    extra = suggestion.extra
    return Item(
        text=suggestion.text,
        kind=_kind(extra.get("kind")),
        author=Author(
            name=suggestion.author_name or str(suggestion.author_id),
            user_id=suggestion.author_id or None,
            language=suggestion.locale or "ru",
        ),
        source=_source(suggestion.source),
        id=suggestion.id,
        created_at=suggestion.created_at,
        chat_id=int(extra["chat_id"]) if "chat_id" in extra else None,
        message_id=int(extra["message_id"]) if "message_id" in extra else None,
        link=suggestion.link,
    )


def _extra(item: Item) -> dict[str, str]:
    extra = {"kind": item.kind.value}
    if item.chat_id is not None:
        extra["chat_id"] = str(item.chat_id)
    if item.message_id is not None:
        extra["message_id"] = str(item.message_id)
    return extra


class SuggestListRepository:
    def __init__(self, box: SuggestionBox, redis: Any, namespace: str = "topics") -> None:
        self.box = box
        self._redis = redis
        self.namespace = namespace

    def _key(self, *parts: object) -> str:
        return ":".join((self.namespace, *map(str, parts)))

    def _origin_key(self, item: Item) -> str | None:
        return self._key("src", *item.origin) if item.origin is not None else None

    async def _claim_origin(self, key: str | None, *, retry_refused: bool) -> bool:
        """Занять сообщение под новый пункт; ``False``, если оно уже занято.

        *retry_refused*: сообщение, которое бот раньше отклонил (лимит, длина),
        можно добавить ещё раз: так админ берёт его в список вручную.
        """
        if key is None:
            return True
        if await self._redis.set(key, REFUSED_ORIGIN, nx=True, ex=ORIGIN_TTL_SECONDS):
            return True
        return retry_refused and _text(await self._redis.get(key) or REFUSED_ORIGIN) == REFUSED_ORIGIN

    async def add(self, item: Item, *, check_limits: bool = True) -> Item | None:
        key = self._origin_key(item)
        if not await self._claim_origin(key, retry_refused=not check_limits):
            return None
        author = item.author
        suggestion = await self.box.submit(
            author.user_id or ANONYMOUS_AUTHOR_ID,
            item.text,
            link=item.link,
            source=item.source.value,
            author_name=author.name,
            locale=author.language,
            extra=_extra(item),
            check_limits=check_limits and author.user_id is not None,
        )
        if key is not None:
            await self._redis.set(key, str(suggestion.id), ex=ORIGIN_TTL_SECONDS)
        return to_item(suggestion)

    async def get(self, item_id: int) -> Item | None:
        suggestion = await self.box.get(item_id)
        return to_item(suggestion) if suggestion is not None else None

    async def items(self) -> list[Item]:
        return [to_item(suggestion) for suggestion in await self.box.find(IN_LIST, LIST_LIMIT)]

    async def count(self) -> int:
        return await self.box.count(IN_LIST)

    async def _move(
        self, item_id: int, expected: SuggestionStatus, target: SuggestionStatus, moderator_id: int | None
    ) -> Item | None:
        suggestion = await self.box.get(item_id)
        if suggestion is None or suggestion.status is not expected:
            return None
        return to_item(await self.box.set_status(item_id, target, moderator_id=moderator_id, notify_author=False))

    async def remove(self, item_id: int, moderator_id: int | None = None) -> Item | None:
        return await self._move(item_id, IN_LIST, REMOVED, moderator_id)

    async def restore(self, item_id: int) -> Item | None:
        return await self._move(item_id, REMOVED, IN_LIST, None)

    async def ban(self, user_id: int, name: str) -> None:
        await self.box.ban(user_id)
        await self._redis.hset(self._key("bans"), str(user_id), name)

    async def unban(self, user_id: int) -> None:
        await self.box.unban(user_id)
        await self._redis.hdel(self._key("bans"), str(user_id))

    async def is_banned(self, user_id: int) -> bool:
        return await self.box.is_banned(user_id)

    async def banned(self) -> dict[int, str]:
        names = {int(_text(k)): _text(v) for k, v in (await self._redis.hgetall(self._key("bans"))).items()}
        return {user_id: names.get(user_id, str(user_id)) for user_id in sorted(await self.box.banned())}
