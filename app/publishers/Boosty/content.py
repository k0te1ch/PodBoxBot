"""Сборка draft.js-контента и медиа-блоков для Boosty create-post.

Boosty хранит тело поста как массив контент-блоков. Текстовый блок —
`{"type":"text","content":"<json>","modificator":""}`, где `content` —
**сама по себе JSON-строка** вида `["<raw text>", "unstyled", []]`
(draft.js-подобная сериализация). Конец логического блока помечается
отдельным блоком `{"type":"text","content":"","modificator":"BLOCK_END"}`.

Аудио и обложка — отдельные блоки, форма сверена с реальным трафиком
редактора (см. `.planning/spikes/boosty-sponsr-feasibility.md`, секция
«Verified upload+publish flow»):
* аудио в `data`:        `{"type":"audio_file","id":<fileId>,"url":"/upload/<fileId>",...}`
* обложка в `teaser_data`: `{"type":"image","id":<fileId>,"url":"https://images.boosty.to/image/<fileId>?...",...}`

Либа `barsikus007/boosty` даёт только парсер (`render_text`), билдера нет —
поэтому формат воспроизводим вручную. Модуль намеренно НЕ импортирует
`boosty` — чистые функции, тестируются без установленной либы.
"""

from __future__ import annotations

import json

# Boosty CDN, отдающий загруженные обложки. Это платформенный endpoint
# (часть протокола create-post), а не конфигурируемый адрес окружения.
IMAGES_CDN = "https://images.boosty.to"


def _text_block(text: str) -> dict[str, str]:
    """Один draft.js текстовый блок. Внутренний слой — отдельный json.dumps."""
    inner = json.dumps([text, "unstyled", []], ensure_ascii=False)
    return {"type": "text", "content": inner, "modificator": ""}


def _block_end() -> dict[str, str]:
    """Маркер конца логического блока."""
    return {"type": "text", "content": "", "modificator": "BLOCK_END"}


def _text_blocks(body: str, chapters: list[list[str]] | None) -> list[dict]:
    """Текстовые блоки: абзацы body + таймлайн глав, каждый закрыт BLOCK_END."""
    blocks: list[dict] = []

    paragraphs = [line for line in (body or "").split("\n") if line.strip()]
    for para in paragraphs:
        blocks.append(_text_block(para))
        blocks.append(_block_end())

    for chapter in chapters or []:
        if not chapter:
            continue
        line = f"{chapter[0]} — {chapter[1]}" if len(chapter) >= 2 else str(chapter[0])
        blocks.append(_text_block(line))
        blocks.append(_block_end())

    return blocks


def build_audio_block(file_id: str, size: int, title: str) -> dict:
    """Блок аудио для поля `data`.

    `url` — относительный `/upload/<fileId>` (так шлёт редактор сразу после
    загрузки; после обработки Boosty сам подменяет на
    `cdn.boosty.to/audio/<fileId>`).
    """
    return {
        "complete": True,
        "id": file_id,
        "size": size,
        "title": title,
        "type": "audio_file",
        "url": f"/upload/{file_id}",
    }


def build_post_data(
    body: str,
    chapters: list[list[str]] | None = None,
    audio: dict | None = None,
) -> str:
    """Собирает значение поля `data` для create-post (внешний json.dumps).

    Абзацы `body` и таймлайн глав идут текстовыми блоками; если передан
    `audio`-блок (см. build_audio_block), он добавляется в конец. Пустой пост
    Boosty не принимает — даём хотя бы один текстовый блок.
    """
    blocks = _text_blocks(body, chapters)

    if not blocks:
        blocks = [_text_block(""), _block_end()]

    if audio is not None:
        blocks.append(audio)

    return json.dumps(blocks, ensure_ascii=False)


def build_teaser_data(image_id: str, teaser_text: str) -> str:
    """Собирает `teaser_data` — то, что видят не-подписчики.

    Первый блок — обложка (image), затем текст-тизер. Форма image-блока
    сверена с трафиком редактора (поля id/uploadId/url/data/rendition/size).
    """
    image_block = {
        "id": image_id,
        "uploadId": image_id,
        "url": f"{IMAGES_CDN}/image/{image_id}?croped=1&mh=150&mw=138",
        "data": {},
        "type": "image",
        "rendition": "",
        "size": 0,
    }
    blocks: list[dict] = [image_block, *_text_blocks(teaser_text, None)]
    return json.dumps(blocks, ensure_ascii=False)
