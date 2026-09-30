"""Текст поста послешоу для площадок без своего формата блоков."""

from __future__ import annotations

from html import escape


def chapter_lines(chapters: list[list[str]] | None) -> list[str]:
    lines = []
    for chapter in chapters or []:
        if not chapter:
            continue
        lines.append(f"{chapter[0]} — {chapter[1]}" if len(chapter) >= 2 else str(chapter[0]))
    return lines


def plain_text(comment: str, chapters: list[list[str]] | None) -> str:
    """Описание и таймкоды обычным текстом (VK)."""
    parts = [(comment or "").strip()]
    lines = chapter_lines(chapters)
    if lines:
        parts.append("\n".join(lines))
    return "\n\n".join(p for p in parts if p)


def html_text(comment: str, chapters: list[list[str]] | None) -> str:
    """Описание абзацами и таймкоды списком (Patreon, Sponsr)."""
    paragraphs = [f"<p>{escape(line)}</p>" for line in (comment or "").split("\n") if line.strip()]
    lines = chapter_lines(chapters)
    if lines:
        paragraphs.append("<p>" + "<br>".join(escape(line) for line in lines) + "</p>")
    return "".join(paragraphs)
