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
    """Номера, отмеченные кнопками под списком."""

    def item_id(self, number: int) -> int | None:
        return self.ids[number - 1] if 1 <= number <= len(self.ids) else None

    def to_json(self) -> str:
        return json.dumps({"token": self.token, "ids": self.ids, "marked": self.marked})

    @classmethod
    def from_json(cls, raw: str | bytes) -> "ListView":
        data = json.loads(raw)
        return cls(token=data["token"], ids=list(data["ids"]), marked=list(data.get("marked", [])))


class ViewStore:
    def __init__(self, redis: Any, namespace: str = "topics") -> None:
        self._redis = redis
        self.namespace = namespace

    def _view_key(self, chat_id: int) -> str:
        return f"{self.namespace}:view:{chat_id}"

    def _undo_key(self, token: str) -> str:
        return f"{self.namespace}:undo:{token}"

    async def _save(self, chat_id: int, view: ListView) -> None:
        await self._redis.set(self._view_key(chat_id), view.to_json(), ex=VIEW_TTL_SECONDS)

    async def remember(self, chat_id: int, item_ids: list[int]) -> ListView:
        """Запомнить только что показанный список; прежний снимок чата заменяется."""
        view = ListView(token=secrets.token_hex(3), ids=list(item_ids))
        await self._save(chat_id, view)
        return view

    async def last(self, chat_id: int) -> ListView | None:
        raw = await self._redis.get(self._view_key(chat_id))
        return ListView.from_json(raw) if raw else None

    async def current(self, chat_id: int, token: str) -> ListView | None:
        """Снимок чата, если кнопка с меткой *token* от него, а не от старого списка."""
        view = await self.last(chat_id)
        return view if view is not None and view.token == token else None

    async def toggle(self, chat_id: int, token: str, number: int) -> ListView | None:
        """Поставить или снять отметку; ``None``, если список уже другой."""
        view = await self.current(chat_id, token)
        if view is None or view.item_id(number) is None:
            return None
        if number in view.marked:
            view.marked.remove(number)
        else:
            view.marked = sorted([*view.marked, number])
        await self._save(chat_id, view)
        return view

    async def keep_removed(self, item_ids: list[int]) -> str:
        """Запомнить удалённые пункты для «Вернуть»; в ответе метка кнопки."""
        token = secrets.token_hex(4)
        await self._redis.set(self._undo_key(token), json.dumps(item_ids), ex=UNDO_TTL_SECONDS)
        return token

    async def take_removed(self, token: str) -> list[int] | None:
        """Пункты для возврата; ``None``, если время вышло или их уже вернули."""
        key = self._undo_key(token)
        raw = await self._redis.get(key)
        if not raw:
            return None
        await self._redis.delete(key)
        return list(json.loads(raw))
