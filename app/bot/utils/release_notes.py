"""Разбор CHANGELOG.md и рассылка релиз-ноута админам.

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

    # parts уже HTML-escaped и разбиты по секциям, каждая < 4096 байт.
    # broadcast_message_to_users -> send_message_to_user умеет принимать
    # list[str] и отправляет каждую часть отдельным сообщением, минуя
    # split_into_messages.
    await broadcast_message_to_users(parts, ADMINS_ID, True, parse_mode=ParseMode.HTML)


def _markdown_inline_to_html(text: str) -> str:
    """HTML-escape text and convert inline `code` spans to <code>…</code>.

    Покрывает CHANGELOG-форматирование (бэктики вокруг идентификаторов).
    Звёздочки/подчёркивания CHANGELOG не использует, так что не трогаем.
    """
    parts = []
    in_code = False
    buf: list[str] = []
    for ch in text:
        if ch == "`":
            parts.append(("code" if in_code else "text", "".join(buf)))
            buf = []
            in_code = not in_code
        else:
            buf.append(ch)
    parts.append(("code" if in_code else "text", "".join(buf)))

    out: list[str] = []
    for kind, chunk in parts:
        escaped = html.escape(chunk, quote=False)
        if kind == "code" and chunk:
            out.append(f"<code>{escaped}</code>")
        else:
            out.append(escaped)
    return "".join(out)


# --- release-please CHANGELOG parsing ---
# release-please пишет CHANGELOG в таком виде:
#   ## [0.4.0](compare-url) (2026-06-01)
#   ### Features
#   * **scope:** summary ([#19](url)) ([hash](url))
# Версию/дату берём из заголовка верхнего (самого свежего) релизного блока,
# секции — из "### ..."-подзаголовков. Старый ручной формат
# (# 0.3.0 / ## Добавлено / дата ДД.ММ.ГГГГ) больше не используется.
_VERSION_HEADING = re.compile(r"^##\s+\[?(\d+\.\d+\.\d+)\]?", re.MULTILINE)
_DATE_IN_HEADING = re.compile(r"\((\d{4}-\d{2}-\d{2})\)")
_SECTION_HEADING = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")

# Английские заголовки секций release-please → русские подписи.
# Неизвестные секции показываем как есть (как в changelog).
_SECTION_LABELS = {
    "Features": "Добавлено",
    "Bug Fixes": "Исправлено",
    "Performance Improvements": "Производительность",
    "Code Refactoring": "Рефакторинг",
    "Reverts": "Откаты",
    "Documentation": "Документация",
    "Tests": "Тесты",
    "Build System": "Сборка",
    "Continuous Integration": "CI",
    "Miscellaneous Chores": "Прочее",
    "Styles": "Стиль",
}


def _format_bullet(text: str) -> str:
    """Очищает один пункт changelog для показа в Telegram (HTML).

    Markdown-ссылки `[text](url)` сворачиваем в `text` (убираем url-шум от
    хэшей коммитов и PR), маркеры жирного `**` отбрасываем, дальше отдаём
    в `_markdown_inline_to_html` — он экранирует HTML и переводит inline
    `code` в <code>.
    """
    text = _MD_LINK.sub(r"\1", text)
    text = text.replace("**", "")
    return _markdown_inline_to_html(text)


async def get_release_note() -> list[str] | None:
    """Read CHANGELOG.md and format the latest release block as HTML chunks.

    Returns a list of HTML-formatted message parts (header + one or more
    per-section messages), each safe to send as a single Telegram message
    in HTML parse-mode. Returns None when CHANGELOG.md is missing,
    unreadable, or has no release block — the broadcast is a courtesy and
    must never crash on_startup.

    Why HTML and not MarkdownV2: changelog entries contain plenty of
    punctuation MarkdownV2 reserves (`!`, `(`, `)`, `.`, `-`, `:`, etc).
    Escaping all of them by hand is error-prone; HTML only requires
    escaping `<`, `>`, `&`, which html.escape() handles for us.
    """
    # CHANGELOG ships at /app/CHANGELOG.md (see Dockerfile COPY), but be
    # forgiving about cwd to keep local dev runs working.
    candidates = [Path("CHANGELOG.md"), Path("/app/CHANGELOG.md")]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        logger.warning("CHANGELOG.md not found; skipping release-note broadcast")
        return None

    try:
        async with aiofiles.open(path) as f:
            content = await f.read()
    except OSError as e:
        logger.warning(f"Failed to read {path}: {e!r}")
        return None

    # Верхний релизный блок: от первого версия-заголовка до следующего.
    headings = list(_VERSION_HEADING.finditer(content))
    if not headings:
        logger.warning("No release block found in CHANGELOG.md; skipping broadcast")
        return None

    first = headings[0]
    block_end = headings[1].start() if len(headings) > 1 else len(content)
    line_end = content.find("\n", first.start())
    heading_line = content[first.start() : line_end if line_end != -1 else len(content)]
    block = content[first.end() : block_end]

    version = first.group(1)
    date_match = _DATE_IN_HEADING.search(heading_line)
    date = date_match.group(1) if date_match else "неизвестно"

    parts: list[str] = [
        f"<b>Бот обновлён!</b>\n\n<b>Список изменений (версия {html.escape(version)}, от {html.escape(date)}):</b>"
    ]

    # Cyrillic в UTF-8 — по 2 байта, так что 4096-байтовый лимит TG
    # достигается раньше, чем кажется по числу символов. Шлём каждую
    # секцию отдельным сообщением; если секция перерастает лимит — режем
    # её по пунктам (см. _pack_html_chunks).
    section_matches = list(_SECTION_HEADING.finditer(block))
    for i, section in enumerate(section_matches):
        name = section.group(1).strip()
        sec_end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(block)
        body = block[section.end() : sec_end]

        bullets: list[str] = []
        for raw in body.split("\n"):
            line = raw.strip()
            if not line.startswith("* "):
                continue
            item = line[2:].strip()
            if item:
                bullets.append(f"• {_format_bullet(item)}")

        if not bullets:
            continue

        label = _SECTION_LABELS.get(name, name)
        heading = f"<i>{html.escape(label)}</i>:"
        parts.extend(_pack_html_chunks(heading, bullets))

    return parts


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
