"""Релиз-ноут для админов: русские заметки к версии из ``release-notes/ru``.

Версию последнего релиза берём из верхнего блока CHANGELOG.md (его ведёт
release-please), а текст для админов из ``release-notes/ru/<версия>.md``:
CHANGELOG собран из английских заголовков коммитов и людям заказчика не
подходит. Нет файла заметок, шлём только номер версии.

Выделено из ``bot_methods`` вместе с :mod:`utils.messaging`.
"""

import html
import re
from pathlib import Path

import aiofiles
import toml
from aiogram.enums import ParseMode
from loguru import logger

from config import ADMINS_ID
from services import redis
from services.none_module import _NoneModule
from utils.messaging import broadcast_message_to_users


async def send_release_note() -> None:
    if not await check_version():
        return
    parts = await get_release_note()
    if not parts:
        return

    # parts уже HTML-escaped и разбиты на части, каждая < 4096 байт.
    # broadcast_message_to_users -> send_message_to_user умеет принимать
    # list[str] и отправляет каждую часть отдельным сообщением, минуя
    # split_into_messages.
    await broadcast_message_to_users(parts, ADMINS_ID, True, parse_mode=ParseMode.HTML)


# release-please пишет заголовок релиза как ``## [0.4.0](compare-url) (2026-06-01)``;
# нужен только номер версии верхнего (самого свежего) блока.
_VERSION_HEADING = re.compile(r"^##\s+\[?(\d+\.\d+\.\d+)\]?", re.MULTILINE)
_BULLET_PREFIXES = ("- ", "* ")
_NOTES_DIR = Path("release-notes") / "ru"


async def _read_text(path: Path) -> str | None:
    try:
        async with aiofiles.open(path, encoding="utf-8") as f:
            return await f.read()
    except OSError as e:
        logger.warning(f"Failed to read {path}: {e!r}")
        return None


def _note_lines(content: str) -> list[str]:
    """Строки файла заметок как HTML: пункты списка с «•», прочие как есть.

    Пустые строки и markdown-заголовки (``# ...``) пропускаем, всё
    остальное экранируем: в заметках пишут обычный текст, не разметку.
    """
    lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(_BULLET_PREFIXES):
            lines.append(f"• {html.escape(line[2:].strip(), quote=False)}")
        else:
            lines.append(html.escape(line, quote=False))
    return lines


async def get_release_note() -> list[str] | None:
    """Release note for the latest CHANGELOG version as TG-sized HTML parts.

    Text comes from ``release-notes/ru/<version>.md`` next to CHANGELOG.md.
    When that file is missing or empty the admins get a one-line
    "updated to version X" message instead of raw English changelog lines.
    Returns None when CHANGELOG.md is missing, unreadable, or has no release
    block: the broadcast is a courtesy and must never crash on_startup.

    HTML parse-mode only needs ``<``, ``>``, ``&`` escaped, which
    html.escape() handles; MarkdownV2 would reserve half the punctuation.
    """
    # CHANGELOG and release-notes ship under /app (see Dockerfile COPY), but
    # be forgiving about cwd to keep local dev runs working.
    candidates = [Path("CHANGELOG.md"), Path("/app/CHANGELOG.md")]
    changelog = next((p for p in candidates if p.is_file()), None)
    if changelog is None:
        logger.warning("CHANGELOG.md not found; skipping release-note broadcast")
        return None

    content = await _read_text(changelog)
    if content is None:
        return None

    heading = _VERSION_HEADING.search(content)
    if heading is None:
        logger.warning("No release block found in CHANGELOG.md; skipping broadcast")
        return None
    version = heading.group(1)  # только цифры и точки, экранировать нечего

    notes_path = changelog.parent / _NOTES_DIR / f"{version}.md"
    notes = await _read_text(notes_path) if notes_path.is_file() else None
    lines = _note_lines(notes) if notes else []
    if not lines:
        logger.warning(f"No release notes at {notes_path}; sending the version only")
        return [f"Бот обновлён до версии {version}."]

    # Cyrillic в UTF-8 по 2 байта, так что 4096-байтовый лимит TG
    # достигается раньше, чем кажется по числу символов: режем по пунктам.
    return _pack_html_chunks(f"<b>Бот обновлён до версии {version}</b>\n\nЧто изменилось:", lines)


# Запас под HTML-теги и небольшой буфер; реальный TG-лимит — 4096 байт.
_TG_MESSAGE_MAX_BYTES = 3800


def _pack_html_chunks(heading: str, bullets: list[str]) -> list[str]:
    """Pack heading + bullets into TG-sized HTML messages.

    Each emitted chunk starts with `heading` so context isn't lost when
    a section spans multiple messages. Bullets are added one by one
    until the next one would push the chunk over _TG_MESSAGE_MAX_BYTES;
    then the chunk is flushed and a new one is started, again with the
    heading. A single bullet wider than the limit goes out on its own —
    TG will trim its tail rather than us rejecting the whole release.
    """
    chunks: list[str] = []
    current = heading
    for bullet in bullets:
        candidate = f"{current}\n{bullet}"
        if len(candidate.encode("utf-8")) <= _TG_MESSAGE_MAX_BYTES:
            current = candidate
            continue
        if current != heading:
            chunks.append(current)
        current = f"{heading}\n{bullet}"
    if current != heading or not chunks:
        chunks.append(current)
    return chunks


async def check_version() -> bool:
    """True if pyproject.toml version differs from what's stored in redis.

    Without redis we have no place to persist the last-seen version, so
    every restart would look like a fresh release — skip silently instead.
    """
    if isinstance(redis, _NoneModule):
        logger.debug("Redis is not configured; skipping version check")
        return False

    bot_version = await redis.get("bot_version")
    current_bot_version = await get_version()

    if not current_bot_version:
        return False

    if current_bot_version != bot_version:
        await redis.set("bot_version", current_bot_version)
        return True
    return False


async def get_version() -> str | None:
    """Версия бота из его же pyproject.toml, либо None если её там нет."""
    async with aiofiles.open("pyproject.toml") as f:
        content = await f.read()

    try:
        return toml.loads(content)["tool"]["poetry"]["version"]
    except KeyError:
        # Раньше тут была цепочка .get(..., {}) — отсутствующая секция была
        # неотличима от отсутствующей версии, и обе тихо давали None.
        logger.warning("pyproject.toml has no tool.poetry.version")
        return None
