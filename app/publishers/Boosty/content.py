"""Сборка draft.js-контента для Boosty create-post.

Boosty хранит тело поста как массив контент-блоков. Текстовый блок —
`{"type":"text","content":"<json>","modificator":""}`, где `content` —
**сама по себе JSON-строка** вида `["<raw text>", "unstyled", []]`
(draft.js-подобная сериализация). Конец логического блока помечается
отдельным блоком `{"type":"text","content":"","modificator":"BLOCK_END"}`.

Либа `barsikus007/boosty` даёт только парсер (`render_text`), билдера нет —
поэтому формат воспроизводим вручную. Подтверждено реверсом
`HOCKI1/py_boosty_api` (см. спайк `.planning/spikes/boosty-sponsr-feasibility.md`).

Модуль намеренно НЕ импортирует `boosty` — чистые функции, тестируются
без установленной либы.
"""

from __future__ import annotations

import json


def _text_block(text: str) -> dict[str, str]:
    """Один draft.js текстовый блок. Внутренний слой — отдельный json.dumps."""
    inner = json.dumps([text, "unstyled", []], ensure_ascii=False)
    return {"type": "text", "content": inner, "modificator": ""}


def _block_end() -> dict[str, str]:
    """Маркер конца логического блока."""
    return {"type": "text", "content": "", "modificator": "BLOCK_END"}


def build_post_data(
    body: str,
    chapters: list[list[str]] | None = None,
) -> str:
    """Собирает значение поля `data` для create-post (внешний json.dumps).

    Параграфы (`body`, разбитый по `\\n`) и таймлайн глав идут отдельными
    текстовыми блоками; каждый абзац закрывается BLOCK_END. Пустые строки
    пропускаются. Результат — JSON-строка, готовая лечь в form-поле `data`.
    """
    blocks: list[dict[str, str]] = []

    paragraphs = [line for line in (body or "").split("\n") if line.strip()]
    for para in paragraphs:
        blocks.append(_text_block(para))
        blocks.append(_block_end())

    if chapters:
        # Таймлайн отдельными строками "MM:SS — Название".
        for chapter in chapters:
            if not chapter:
                continue
            if len(chapter) >= 2:
                line = f"{chapter[0]} — {chapter[1]}"
            else:
                line = str(chapter[0])
            blocks.append(_text_block(line))
            blocks.append(_block_end())

    if not blocks:
        # Boosty не принимает пустой пост; даём пустой текстовый блок.
        blocks.append(_text_block(""))
        blocks.append(_block_end())

    return json.dumps(blocks, ensure_ascii=False)
