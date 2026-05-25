"""Persists validated podcast template info as a sidecar JSON next to the mp3.

Telegram doesn't include ``reply_to_message`` in callback updates for audio
messages, so we can't recover the template text on button presses. Instead,
right after the audio is tagged and sent, we write ``<mp3_filename>.json``
next to it in ``FILES_PATH``. Subsequent callbacks look up the sidecar by
``callback.message.audio.file_name``.

This trades Redis for a tiny file alongside the mp3. The sidecar is bound to
the audio (moves with it, survives restarts) and is removed together with
old mp3s by ``clear_old_mp3_files``.
"""

import json
from pathlib import Path
from typing import Any

import aiofiles
from loguru import logger

from config import FILES_PATH


def _sidecar_path(audio_file_name: str) -> Path:
    return FILES_PATH / f"{audio_file_name}.json"


async def save(audio_file_name: str, info: dict[str, Any], type_episode: str) -> None:
    path = _sidecar_path(audio_file_name)
    payload = json.dumps({"info": info, "type_episode": type_episode}, ensure_ascii=False, indent=2)
    try:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(payload)
        logger.debug(f"template_store.save: wrote sidecar {path.name}")
    except Exception as e:
        logger.error(f"template_store.save failed for {audio_file_name}: {e}")


async def load(audio_file_name: str) -> dict[str, Any] | None:
    path = _sidecar_path(audio_file_name)
    if not path.exists():
        return None
    try:
        async with aiofiles.open(path, encoding="utf-8") as f:
            raw = await f.read()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"template_store.load failed for {audio_file_name}: {e}")
        return None
