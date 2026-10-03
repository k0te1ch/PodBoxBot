"""Одно сообщение о ходе долгой операции: шаги с отметками и прогресс.

Бот не молчит, пока скачивает mp3, ставит теги или отправляет файл: он
присылает одно сообщение и правит его. Так чат не дёргается от цепочки
«начал», «продолжаю», «готово», а админ видит, что сделано, что идёт сейчас
и сколько осталось::

    🎙 Основной эпизод
    ✅ Файл получен · 27,4 МБ
    ⏳ Узнаю номер выпуска · 4 с
    ▫️ Жду описание

Telegram ограничивает частоту правок, поэтому промежуточные обновления
уходят не чаще раза в :data:`MIN_INTERVAL` секунд; смена шага и итог
отправляются сразу.
"""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from enum import StrEnum
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from loguru import logger

from services.i18n import t

MIN_INTERVAL = 2.0
"""Секунд между промежуточными правками одного сообщения."""

TICK_INTERVAL = 5.0
"""Как часто обновлять «идёт уже N с» у шага без прогресса."""

SLOW_AFTER = 60.0
"""После стольких секунд шаг помечается как необычно долгий."""

BAR_WIDTH = 10
MEGABYTE = 1024 * 1024


class StepState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"


MARKS = {StepState.PENDING: "▫️", StepState.ACTIVE: "⏳", StepState.DONE: "✅", StepState.FAILED: "❌"}


def human_size(size: float, locale: str = "ru") -> str:
    """«27,4 МБ» или «812 КБ»: размер файла так, как его пишут по-русски (в en с точкой)."""
    if size < MEGABYTE:
        return f"{size / 1024:.0f} {t('status_kilobytes', locale)}"
    megabytes = f"{size / MEGABYTE:.1f}"
    if locale == "ru":
        megabytes = megabytes.replace(".", ",")
    return f"{megabytes} {t('status_megabytes', locale)}"


def human_seconds(seconds: float, locale: str = "ru") -> str:
    """«40 с» или «2 мин 05 с»."""
    seconds = max(0, round(seconds))
    if seconds < 60:
        return t("status_seconds", locale, seconds=seconds)
    return t("status_minutes", locale, minutes=seconds // 60, seconds=f"{seconds % 60:02d}")


def bar(fraction: float) -> str:
    """Полоса прогресса из десяти делений."""
    filled = round(min(max(fraction, 0.0), 1.0) * BAR_WIDTH)
    return "▰" * filled + "▱" * (BAR_WIDTH - filled)


def progress_detail(done: float, total: float, elapsed: float, locale: str = "ru") -> str:
    """«45% ▰▰▰▰▱▱▱▱▱▱ 12,3 из 27,4 МБ, ещё ~20 с»."""
    if total <= 0:
        return human_size(done, locale)
    fraction = min(done / total, 1.0)
    text = f"{fraction * 100:.0f}% {bar(fraction)} " + t(
        "status_of", locale, done=human_size(done, locale).rsplit(" ", 1)[0], total=human_size(total, locale)
    )
    if 0 < fraction < 1 and elapsed >= 2:
        text += ", " + t("status_left", locale, time=human_seconds(elapsed / fraction - elapsed, locale))
    return text


@dataclass
class Step:
    key: str
    state: StepState = StepState.PENDING
    detail: str = ""
    started: float = 0.0


class StatusMessage:
    """Сообщение с шагами операции, которое бот правит по ходу дела.

    Названия шагов берутся из локали: ``status_<key>`` для шага, который
    ждёт или идёт, и ``status_<key>_done`` для выполненного (если такого
    ключа нет, остаётся первое).
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        title: str,
        steps: list[str],
        locale: str = "ru",
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.title = title
        self.locale = locale
        self.steps = {key: Step(key) for key in steps}
        self._clock = clock
        self._last_edit = 0.0
        self._shown = ""
        # Правки идут по одной: прогресс отправки файла приходит из фоновых
        # задач, а Telegram отменяет правку, которую догнала следующая.
        self._lock = asyncio.Lock()

    # --- что показать ---

    def _label(self, step: Step) -> str:
        if step.state is StepState.DONE:
            done = t(f"status_{step.key}_done", self.locale)
            if done != f"status_{step.key}_done":
                return done
        return t(f"status_{step.key}", self.locale)

    def _line(self, step: Step) -> str:
        line = f"{MARKS[step.state]} {self._label(step)}"
        detail = step.detail
        if step.state is StepState.ACTIVE and not detail:
            elapsed = self._clock() - step.started
            if elapsed >= SLOW_AFTER:
                detail = t("status_slow", self.locale, time=human_seconds(elapsed, self.locale))
            elif elapsed >= TICK_INTERVAL:
                detail = human_seconds(elapsed, self.locale)
        if detail:
            line += (": " if "%" in detail else " · ") + detail
        return line

    def render(self) -> str:
        return "\n".join([f"<b>{self.title}</b>", *(self._line(step) for step in self.steps.values())])

    # --- шаги ---

    async def begin(self, key: str) -> None:
        """Шаг начался: сообщение обновляется сразу."""
        step = self.steps[key]
        step.state, step.detail, step.started = StepState.ACTIVE, "", self._clock()
        await self.update(force=True)

    async def progress(self, key: str, done: float, total: float) -> None:
        """Ход шага с известным объёмом: правка не чаще :data:`MIN_INTERVAL`."""
        step = self.steps[key]
        if step.state is not StepState.ACTIVE:
            return
        step.detail = progress_detail(done, total, self._clock() - step.started, self.locale)
        await self.update()

    async def done(self, key: str, detail: str = "") -> None:
        step = self.steps[key]
        step.state, step.detail = StepState.DONE, detail
        await self.update(force=True)

    async def fail(self, key: str, reason: str) -> None:
        """Шаг не удался: причина остаётся в сообщении. *reason* в HTML."""
        step = self.steps[key]
        step.state, step.detail = StepState.FAILED, reason
        await self.update(force=True)

    @contextlib.asynccontextmanager
    async def ticking(self, key: str) -> AsyncIterator[None]:
        """Шаг без прогресса: пока он идёт, в сообщении тикает «уже N с»."""
        await self.begin(key)

        async def tick() -> None:
            while True:
                await asyncio.sleep(TICK_INTERVAL)
                await self.update()

        task = asyncio.create_task(tick())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # --- правка сообщения ---

    async def update(self, *, force: bool = False, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        if not force and (self.render() == self._shown or self._clock() - self._last_edit < MIN_INTERVAL):
            return
        async with self._lock:
            # Текст собирается под замком: отправляется самое свежее состояние.
            text = self.render()
            if text != self._shown:
                await self._edit(text, reply_markup, final=force)

    async def replace(self, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        """Заменяет всё сообщение итоговым текстом."""
        async with self._lock:
            await self._edit(text, reply_markup, final=True)

    async def _edit(self, text: str, reply_markup: InlineKeyboardMarkup | None, *, final: bool) -> None:
        self._last_edit = self._clock()
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id, message_id=self.message_id, text=text, reply_markup=reply_markup
            )
        except TelegramRetryAfter as error:
            # Промежуточную правку проще пропустить, чем ждать: следующая
            # покажет более свежее состояние. Итог дожидается.
            if not final:
                self._last_edit = self._clock() + error.retry_after
                return
            await asyncio.sleep(error.retry_after)
            await self._edit(text, reply_markup, final=False)
            return
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error):
                logger.warning(f"status message not updated: {error!r}")
                return
        except TelegramAPIError as error:
            logger.warning(f"status message not updated: {error!r}")
            return
        self._shown = text


def html(text: object) -> str:
    """Чужой текст (имя файла, ошибка) для вставки в статус."""
    return escape(str(text))
