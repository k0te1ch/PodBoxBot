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

Табло живёт в памяти процесса: после перезапуска бота события по старым
публикациям правят сообщение обычным текстом, как раньше
(:mod:`services.telegram_updater`).
"""

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import Message
from loguru import logger

from config import TIMEZONE
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

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._by_audio: OrderedDict[tuple[int, int], Board] = OrderedDict()
        self._by_status: dict[tuple[str, str], Board] = {}
        self._clock = clock

    def get(self, chat_id: object, message_id: object) -> Board | None:
        return self._by_status.get((str(chat_id), str(message_id)))

    def recent(self) -> list[Board]:
        """Табло от новых к старым: для ``/status``."""
        return list(reversed(self._by_audio.values()))

    async def open(self, audio: Message, platform: str, title: str) -> "StatusRef":
        """Строка площадки в табло этого файла; первое нажатие создаёт табло.

        В ответе адрес сообщения-табло: хендлер кладёт его в запрос
        публикации, и события publisher'а правят это сообщение.
        """
        key = (audio.chat.id, audio.message_id)
        board = self._by_audio.get(key)
        if board is not None:
            self._by_audio.move_to_end(key)
            board.rows[platform] = Row(platform)
            await self._edit(board, final=True)
            return StatusRef(board.chat_id, board.message_id)
        board = Board(audio.bot, audio.chat.id, 0, title, {platform: Row(platform)})
        # Табло регистрируется до отправки: второе нажатие, пришедшее в ту же
        # секунду, найдёт его и не заведёт второе сообщение.
        self._by_audio[key] = board
        async with board.lock:
            html = board.html()
            sent = await rich.send(audio.bot, audio.chat.id, html, board.text())
            board.message_id, board.last_edit, board.shown = sent.message_id, self._clock(), html
        self._by_status[(str(board.chat_id), str(board.message_id))] = board
        while len(self._by_audio) > MAX_BOARDS:
            _key, old = self._by_audio.popitem(last=False)
            self._by_status.pop((str(old.chat_id), str(old.message_id)), None)
        return StatusRef(board.chat_id, board.message_id)

    async def update(
        self,
        board: Board,
        platform: str,
        state: str,
        text: str,
        *,
        url: str | None = None,
        error: str | None = None,
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
        дошла последней, она несёт самое свежее состояние всех площадок.
        """
        async with board.lock:
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
                    logger.warning(f"publish board was not updated: {error!r}")
                    return
                else:
                    board.shown = html
                    return


@dataclass(frozen=True)
class StatusRef:
    """Адрес сообщения-табло для запроса публикации."""

    chat_id: int
    message_id: int


boards = PublishBoards()
