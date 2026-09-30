"""Где лежит очередь тем.

Хендлеры и меню работают только с протоколом :class:`TopicRepository`.
Реализация, :class:`SuggestTopicRepository`, держит темы в очереди модуля
``suggest`` из sagenza-tgbot-sdk (:class:`SuggestionBox` поверх
``RedisSuggestStore``): там же лимит на автора и бан-лист. Все пути приёма
(хештег, анкета в группе, анкета в личке) пишут в эту одну очередь.

Своего в адаптере две вещи:

* ``<ns>:src:<chat>:<message>`` в Redis: метка, что сообщение чата уже
  стало темой: Telegram может доставить апдейт повторно, а у SDK отсечки по
  сообщению нет. Метка ставится до проверки лимитов, так что повтор
  отклонённого сообщения тоже молча отсекается;
* автор без id (пост от имени канала, анонимный админ) хранится с
  ``author_id=0`` и лимитом не ограничивается: считать его не по кому.
"""

from typing import Any, Protocol

from sagenza_tgbot_sdk.suggest import Suggestion, SuggestionBox, SuggestionNotFoundError

from services.topics.models import Author, Topic, TopicSource, TopicStatus

DEFAULT_LIST_LIMIT = 200
# Метка сообщения нужна против повторной доставки апдейта, дольше месяца её
# держать незачем.
ORIGIN_TTL_SECONDS = 30 * 24 * 3600
ANONYMOUS_AUTHOR_ID = 0


class TopicRepository(Protocol):
    async def add(self, topic: Topic) -> Topic | None:
        """Сохранить тему и выдать ей id; ``None``, если это сообщение уже сохранено.

        Отказ по лимиту или бану: :class:`SuggestionRejectedError` из SDK.
        """

    async def get(self, topic_id: int) -> Topic | None: ...

    async def list(self, status: TopicStatus, limit: int = DEFAULT_LIST_LIMIT) -> list[Topic]:
        """Темы в статусе, свежие сверху."""

    async def count(self, status: TopicStatus) -> int: ...

    async def set_status(
        self, topic_id: int, status: TopicStatus, *, note: str | None = None, moderator_id: int | None = None
    ) -> Topic | None:
        """Перевести тему в статус; ``None``, если темы нет. *note*: номер выпуска."""

    async def ban(self, user_id: int) -> None: ...

    async def unban(self, user_id: int) -> None: ...

    async def is_banned(self, user_id: int) -> bool: ...


def to_topic(suggestion: Suggestion) -> Topic:
    extra = suggestion.extra
    return Topic(
        text=suggestion.text,
        author=Author(
            name=suggestion.author_name or str(suggestion.author_id),
            user_id=suggestion.author_id or None,
            language=suggestion.locale or "ru",
        ),
        source=TopicSource(suggestion.source),
        status=suggestion.status,
        id=suggestion.id,
        created_at=suggestion.created_at,
        chat_id=int(extra["chat_id"]) if "chat_id" in extra else None,
        message_id=int(extra["message_id"]) if "message_id" in extra else None,
        link=suggestion.link,
        note=suggestion.note,
    )


def _extra(topic: Topic) -> dict[str, str]:
    extra = {}
    if topic.chat_id is not None:
        extra["chat_id"] = str(topic.chat_id)
    if topic.message_id is not None:
        extra["message_id"] = str(topic.message_id)
    return extra


class SuggestTopicRepository:
    def __init__(self, box: SuggestionBox, redis: Any, namespace: str = "topics") -> None:
        self.box = box
        self._redis = redis
        self.namespace = namespace

    async def _claim_origin(self, topic: Topic) -> bool:
        if topic.origin is None:
            return True
        key = ":".join((self.namespace, "src", *map(str, topic.origin)))
        return bool(await self._redis.set(key, 1, nx=True, ex=ORIGIN_TTL_SECONDS))

    async def add(self, topic: Topic) -> Topic | None:
        if not await self._claim_origin(topic):
            return None
        author = topic.author
        suggestion = await self.box.submit(
            author.user_id or ANONYMOUS_AUTHOR_ID,
            topic.text,
            link=topic.link,
            source=topic.source.value,
            author_name=author.name,
            locale=author.language,
            extra=_extra(topic),
            check_limits=author.user_id is not None,
        )
        return to_topic(suggestion)

    async def get(self, topic_id: int) -> Topic | None:
        suggestion = await self.box.get(topic_id)
        return to_topic(suggestion) if suggestion is not None else None

    async def list(self, status: TopicStatus, limit: int = DEFAULT_LIST_LIMIT) -> list[Topic]:
        # SDK отдаёт старые сверху, а ведущим нужны свежие: берём хвост и разворачиваем.
        offset = max(await self.box.count(status) - limit, 0)
        suggestions = await self.box.find(status, limit, offset)
        return [to_topic(suggestion) for suggestion in reversed(suggestions)]

    async def count(self, status: TopicStatus) -> int:
        return await self.box.count(status)

    async def set_status(
        self, topic_id: int, status: TopicStatus, *, note: str | None = None, moderator_id: int | None = None
    ) -> Topic | None:
        try:
            suggestion = await self.box.set_status(topic_id, status, moderator_id=moderator_id, note=note)
        except SuggestionNotFoundError:
            return None
        return to_topic(suggestion)

    async def ban(self, user_id: int) -> None:
        await self.box.ban(user_id)

    async def unban(self, user_id: int) -> None:
        await self.box.unban(user_id)

    async def is_banned(self, user_id: int) -> bool:
        return await self.box.is_banned(user_id)
