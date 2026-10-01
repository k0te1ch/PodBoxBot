"""Что админ видел последним и что можно вернуть.

Номера в «удали 1, 3» относятся к списку, который бот показал в этом чате
последним, а не к текущему: пока ведущий читает, слушатели добавляют пункты,
и номера не должны съезжать. Поэтому при каждом показе запоминается снимок
«номер → id пункта». У снимка есть метка: по ней кнопки под старым списком
узнают, что они устарели.

Удалённое помнится отдельно и недолго: это кнопка «Вернуть».
"""

import json
import secrets
from dataclasses import dataclass, field
from typing import Any

VIEW_TTL_SECONDS = 24 * 3600
UNDO_TTL_SECONDS = 10 * 60


@dataclass
class ListView:
    token: str
    ids: list[int]
    """Пункты в показанном порядке: номер ``n`` — это ``ids[n - 1]``."""
    marked: list[int] = field(default_factory=list)
    """Номера, отмеченные кнопками под списком, по возрастанию."""
    last_message_id: int | None = None
    """Последнее сообщение списка: под ним кнопка «Удалить отмеченные (N)»."""
    last_numbers: list[int] = field(default_factory=list)
    """Номера пунктов в этом сообщении: по ним пересобирается его клавиатура."""

    def item_id(self, number: int) -> int | None:
        return self.ids[number - 1] if 1 <= number <= len(self.ids) else None


class ViewStore:
    """Снимки и «Вернуть» в Redis.

    * ``<ns>:view:<chat>``: метка и id пунктов последнего показанного списка;
    * ``<ns>:marks:<chat>:<метка>``: множество отмеченных номеров. Отдельным
      множеством, чтобы два быстрых нажатия не затирали отметки друг друга;
    * ``<ns>:undo:<метка>``: id удалённых пунктов, пока их можно вернуть.
    """

    def __init__(self, redis: Any, namespace: str = "topics") -> None:
        self._redis = redis
        self.namespace = namespace

    def _view_key(self, chat_id: int) -> str:
        return f"{self.namespace}:view:{chat_id}"

    def _marks_key(self, chat_id: int, token: str) -> str:
        return f"{self.namespace}:marks:{chat_id}:{token}"

    def _undo_key(self, token: str) -> str:
        return f"{self.namespace}:undo:{token}"

    @staticmethod
    def new_view(item_ids: list[int], marked: list[int] | None = None) -> ListView:
        """Снимок под список, который бот сейчас покажет; в Redis его кладёт :meth:`remember`."""
        return ListView(token=secrets.token_hex(3), ids=list(item_ids), marked=sorted(set(marked or [])))

    async def remember(self, chat_id: int, view: ListView) -> None:
        """Запомнить показанный список; прежний снимок чата заменяется."""
        raw = json.dumps(
            {"token": view.token, "ids": view.ids, "last": view.last_message_id, "numbers": view.last_numbers}
        )
        await self._redis.set(self._view_key(chat_id), raw, ex=VIEW_TTL_SECONDS)
        if view.marked:
            key = self._marks_key(chat_id, view.token)
            await self._redis.sadd(key, *view.marked)
            await self._redis.expire(key, VIEW_TTL_SECONDS)

    async def last(self, chat_id: int) -> ListView | None:
        raw = await self._redis.get(self._view_key(chat_id))
        if not raw:
            return None
        data = json.loads(raw)
        marks = await self._redis.smembers(self._marks_key(chat_id, data["token"]))
        return ListView(
            token=data["token"],
            ids=list(data["ids"]),
            marked=sorted(int(mark) for mark in marks),
            last_message_id=data.get("last"),
            last_numbers=list(data.get("numbers", [])),
        )

    async def current(self, chat_id: int, token: str) -> ListView | None:
        """Снимок чата, если кнопка с меткой *token* от него, а не от старого списка."""
        view = await self.last(chat_id)
        return view if view is not None and view.token == token else None

    async def toggle(self, chat_id: int, token: str, number: int) -> ListView | None:
        """Поставить или снять отметку; ``None``, если список уже другой."""
        view = await self.current(chat_id, token)
        if view is None or view.item_id(number) is None:
            return None
        key = self._marks_key(chat_id, token)
        if not await self._redis.srem(key, number):
            await self._redis.sadd(key, number)
            await self._redis.expire(key, VIEW_TTL_SECONDS)
        return await self.current(chat_id, token)

    async def keep_removed(self, item_ids: list[int]) -> str:
        """Запомнить удалённые пункты для «Вернуть»; в ответе метка кнопки."""
        token = secrets.token_hex(4)
        await self._redis.set(self._undo_key(token), json.dumps(item_ids), ex=UNDO_TTL_SECONDS)
        return token

    async def take_removed(self, token: str) -> list[int] | None:
        """Пункты для возврата; ``None``, если время вышло или их уже вернули.

        Забираются одной командой: второе нажатие «Вернуть» уже ничего не найдёт.
        """
        raw = await self._redis.getdel(self._undo_key(token))
        return list(json.loads(raw)) if raw else None
