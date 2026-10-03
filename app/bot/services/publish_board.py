"""Статус публикации выпуска: одна таблица на все площадки.

Раньше каждая кнопка публикации присылала своё сообщение, и после FTP, сайта
и Boosty в чате висели три разных статуса. Теперь у готового файла одно
сообщение-табло: строка на площадку, что с ней сейчас, ссылка на результат и
время последнего события::

    Выпуск 1002: публикация
    Площадка | Состояние                 | Ссылка  | Когда
    FTP      | ✅ файл загружен           |         | 12:04
    Сайт     | ⏳ проверка, что пост есть |         | 12:05
    Boosty   | ❌ ошибка на шаге publish  |         | 12:05

    ❌ Boosty: 403 Forbidden

Табло хранится в Redis (:mod:`services.publish_board_store`) и переживает
перезапуск бота: событие по старой публикации находит своё табло и правит
в нём строку. В памяти процесса лежит только кеш последних табло и замок
каждого: правки одного табло идут по одной.

Если сообщение-табло удалили, а по публикации пришло новое событие, бот
присылает табло заново: итог публикации не должен пропасть вместе с
сообщением.
"""

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import Message
from loguru import logger

from config import TIMEZONE
from services.publish_board_store import BoardStore
from services.redis import redis
from utils import rich

QUEUED = "queued"
RUNNING = "running"
RETRY = "retry"
DONE = "done"
FAILED = "failed"
FINAL = (DONE, FAILED)

PLATFORM_TITLES = {
    "ftp": "FTP",
    "wp": "Сайт",
    "boosty": "Boosty",
    "vk": "VK Donut",
    "patreon": "Patreon",
    "sponsr": "Sponsr",
}

HEADERS = ["Площадка", "Состояние", "Ссылка", "Когда"]
QUEUED_TEXT = "⏳ запрос принят, жду сервис публикации"
STARTING_TEXT = "⏳ отправляю запрос"

MAX_BOARDS = 64
"""Сколько табло держать в памяти; остальные поднимаются из Redis по событию."""
MIN_INTERVAL = 2.0
"""Секунд между промежуточными правками табло (ход загрузки файла)."""


def platform_title(platform: str) -> str:
    return PLATFORM_TITLES.get(platform, platform)


@dataclass
class Row:
    platform: str
    state: str = QUEUED
    text: str = STARTING_TEXT
    """Состояние словами, уже в HTML."""
    url: str | None = None
    error: str | None = None
    at: float = field(default_factory=time.time)


@dataclass
class Board:
    bot: Bot
    chat_id: int
    message_id: int
    title: str
    rows: dict[str, Row] = field(default_factory=dict)
    last_edit: float = 0.0
    shown: str = ""
    """Что сейчас в сообщении: одинаковое второй раз не отправляется."""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    """Правки табло идут по одной. События площадок приходят одновременно с
    нажатиями кнопок, а Telegram отменяет правку, которую догнала следующая:
    без очереди в сообщении мог остаться не последний вариант."""
    ref_id: int = 0
    """Id сообщения, которым табло отправили впервые: его publisher'ы
    возвращают в событиях. ``message_id`` отличается от него, только если
    табло пришлось прислать заново."""
    audio_id: int | None = None
    """Сообщение с готовым файлом, под которым нажимают кнопки площадок."""

    def __post_init__(self) -> None:
        self.ref_id = self.ref_id or self.message_id

    def dump(self) -> dict:
        """Табло для Redis: всё, кроме того, что живёт только в процессе."""
        return {
            "chat_id": self.chat_id,
            "ref_id": self.ref_id,
            "message_id": self.message_id,
            "audio_id": self.audio_id,
            "title": self.title,
            "rows": [asdict(row) for row in self.rows.values()],
        }

    @classmethod
    def restore(cls, bot: Bot, data: dict) -> "Board":
        rows = {row["platform"]: Row(**row) for row in data["rows"]}
        return cls(
            bot,
            int(data["chat_id"]),
            int(data["message_id"]),
            data["title"],
            rows,
            ref_id=int(data["ref_id"]),
            audio_id=data.get("audio_id"),
        )

    def when(self, row: Row) -> str:
        return datetime.fromtimestamp(row.at, TIMEZONE).strftime("%H:%M")

    def html(self) -> str:
        rows = [
            [
                escape(platform_title(row.platform)),
                row.text,
                f'<a href="{escape(row.url)}">открыть</a>' if row.url else "",
                self.when(row),
            ]
            for row in self.rows.values()
        ]
        errors = "".join(
            f"<p>❌ <b>{escape(platform_title(row.platform))}</b>: <code>{escape(row.error)}</code></p>"
            for row in self.rows.values()
            if row.error
        )
        return f"<h4>{escape(self.title)}</h4>{rich.table(HEADERS, rows)}{errors}"

    def text(self) -> str:
        """То же обычным текстом: для клиентов и серверов без rich-сообщений."""
        lines = [f"<b>{escape(self.title)}</b>"]
        for row in self.rows.values():
            line = f"{escape(platform_title(row.platform))}: {row.text} ({self.when(row)})"
            if row.url:
                line += f"\n{escape(row.url)}"
            if row.error:
                line += f"\n<code>{escape(row.error)}</code>"
            lines.append(line)
        return "\n".join(lines)


class PublishBoards:
    """Табло по сообщениям: ищутся и по готовому файлу, и по своему сообщению."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, store: BoardStore | None = None) -> None:
        self._by_audio: dict[tuple[int, int], Board] = {}
        self._by_status: OrderedDict[tuple[str, str], Board] = OrderedDict()
        self._clock = clock
        self._store = store or BoardStore(None)
        self._bot: Bot | None = None
        self._registry_lock = asyncio.Lock()
        """Поиск и заведение табло идут по одному: два события, пришедшие
        сразу после перезапуска, должны получить один объект с одним замком,
        иначе их правки снова обгонят друг друга."""

    def bind(self, bot: Bot) -> None:
        """Бот, которым правятся табло, поднятые из Redis."""
        self._bot = bot

    async def get(self, chat_id: object, message_id: object) -> Board | None:
        """Табло по адресу из события publisher'а: из памяти, а после
        перезапуска из Redis."""
        key = (str(chat_id), str(message_id))
        board = self._by_status.get(key)
        if board is not None or not self._store.available:
            return board
        async with self._registry_lock:
            return self._by_status.get(key) or await self._load(*key)

    async def recent(self, limit: int = MAX_BOARDS) -> list[Board]:
        """Табло от новых к старым: для ``/status``."""
        refs = await self._store.recent(limit)
        if refs is None:
            return list(reversed(self._by_status.values()))[:limit]
        found = [await self.get(chat_id, ref_id) for chat_id, ref_id in refs]
        return [board for board in found if board is not None]

    async def open(self, audio: Message, platform: str, title: str) -> "StatusRef":
        """Строка площадки в табло этого файла; первое нажатие создаёт табло.

        В ответе адрес сообщения-табло: хендлер кладёт его в запрос
        публикации, и события publisher'а правят это сообщение.
        """
        key = (audio.chat.id, audio.message_id)
        self._bot = audio.bot
        async with self._registry_lock:
            board = self._by_audio.get(key)
            if board is None and (ref_id := await self._store.ref_of_audio(*key)):
                board = self._by_status.get((str(key[0]), str(ref_id))) or await self._load(key[0], ref_id)
            created = board is None
            if created:
                board = Board(audio.bot, audio.chat.id, 0, title, {platform: Row(platform)}, audio_id=audio.message_id)
                # Табло регистрируется до отправки: второе нажатие, пришедшее в
                # ту же секунду, найдёт его и не заведёт второе сообщение.
                self._by_audio[key] = board
        if not created:
            board.rows[platform] = Row(platform)
            await self._edit(board, final=True)
            return StatusRef(board.chat_id, board.ref_id)
        async with board.lock:
            html = board.html()
            try:
                sent = await rich.send(audio.bot, audio.chat.id, html, board.text())
            except Exception:
                self._by_audio.pop(key, None)
                raise
            board.message_id = board.ref_id = sent.message_id
            board.last_edit, board.shown = self._clock(), html
            self._remember(board)
            await self._store.save(board.dump())
        return StatusRef(board.chat_id, board.ref_id)

    async def _load(self, chat_id: object, ref_id: object) -> Board | None:
        """Табло из Redis в кеш; вызывается под замком реестра."""
        data = await self._store.load(chat_id, ref_id)
        if data is None:
            return None
        if self._bot is None:
            logger.warning("publish board is stored, but there is no bot to edit it with")
            return None
        board = Board.restore(self._bot, data)
        self._remember(board)
        return board

    def _remember(self, board: Board) -> None:
        self._by_status[(str(board.chat_id), str(board.ref_id))] = board
        if board.audio_id is not None:
            self._by_audio[(board.chat_id, board.audio_id)] = board
        while len(self._by_status) > MAX_BOARDS:
            _key, old = self._by_status.popitem(last=False)
            if old.audio_id is not None:
                self._by_audio.pop((old.chat_id, old.audio_id), None)

    async def update(
        self, board: Board, platform: str, state: str, text: str, *, url: str | None = None, error: str | None = None
    ) -> None:
        """Новое состояние площадки. Ход после итога не затирает итог, а
        промежуточные правки идут не чаще :data:`MIN_INTERVAL`."""
        row = board.rows.setdefault(platform, Row(platform))
        if row.state in FINAL and state not in FINAL:
            logger.debug(f"publish board: {platform} progress after the result ignored")
            return
        row.state, row.text, row.at = state, text, time.time()
        row.url, row.error = url or row.url, error
        final = state in FINAL
        if not final and state == RUNNING and self._clock() - board.last_edit < MIN_INTERVAL:
            return
        await self._edit(board, final=final)

    async def _edit(self, board: Board, *, final: bool) -> None:
        """Правит табло; итог пережидает flood-лимит, промежуточное состояние нет.

        Текст собирается под замком, в момент отправки: какая бы правка ни
        дошла последней, она несёт самое свежее состояние всех площадок. Там
        же, под замком, табло пишется в Redis: записи тоже идут по одной.
        """
        async with board.lock:
            if not board.message_id:
                return
            await self._store.save(board.dump())
            for attempt in (1, 2):
                html = board.html()
                if html == board.shown:
                    return
                board.last_edit = self._clock()
                try:
                    await rich.edit(board.bot, board.chat_id, board.message_id, html, board.text())
                except TelegramRetryAfter as error:
                    if not final or attempt == 2:
                        board.last_edit = self._clock() + error.retry_after
                        logger.warning(f"publish board hit the flood limit: {error}")
                        return
                    await asyncio.sleep(error.retry_after)
                except TelegramAPIError as error:
                    if rich.is_gone(error):
                        await self._resend(board, html)
                    else:
                        logger.warning(f"publish board was not updated: {error!r}")
                    return
                else:
                    board.shown = html
                    return

    async def _resend(self, board: Board, html: str) -> None:
        """Табло удалили из чата: оно приходит заново, адрес в событиях прежний."""
        try:
            sent = await rich.send(board.bot, board.chat_id, html, board.text())
        except TelegramAPIError as error:
            logger.warning(f"publish board was deleted and could not be sent again: {error!r}")
            return
        logger.info(f"publish board {board.ref_id} was deleted from the chat, sent again as {sent.message_id}")
        board.message_id, board.shown = sent.message_id, html
        await self._store.save(board.dump())


@dataclass(frozen=True)
class StatusRef:
    """Адрес сообщения-табло для запроса публикации."""

    chat_id: int
    message_id: int


boards = PublishBoards(store=BoardStore(redis))
