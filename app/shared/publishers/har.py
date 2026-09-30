"""Выжимка HAR веб-редактора: какие запросы он шлёт, без значений.

Для площадок без API (Sponsr, Patreon) протокол публикации снимается из
HAR: владелец публикует пост руками в браузере с открытыми DevTools и
сохраняет HAR. Выжимка показывает метод, путь, тип тела, имена полей и
статус ответа — этого хватает, чтобы дописать клиент. Значения полей,
куки и заголовки авторизации не выводятся: HAR содержит сессию.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

_SKIP_SUFFIXES = (".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".woff", ".woff2", ".ico", ".gif", ".webp")


def _keys(text: str | None, mime: str) -> str:
    if not text:
        return ""
    if "json" in mime:
        try:
            body = json.loads(text)
        except ValueError:
            return "<json?>"
        return _shape(body)
    if "form-urlencoded" in mime:
        return ", ".join(sorted({k for k, _ in parse_qsl(text, keep_blank_values=True)}))
    if "multipart" in mime:
        return "<multipart>"
    return f"<{len(text)} bytes>"


def _shape(value, depth: int = 0) -> str:
    if depth > 3:
        return "…"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {_shape(v, depth + 1)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + (_shape(value[0], depth + 1) if value else "") + "]"
    return type(value).__name__


def summarize(har_path: str | Path, host: str) -> list[str]:
    """Строки вида ``POST /path  form: a, b  → 200 {id: int}`` для хоста."""
    log = json.loads(Path(har_path).read_text(encoding="utf-8"))["log"]
    lines = []
    for entry in log.get("entries", []):
        request = entry["request"]
        url = urlsplit(request["url"])
        if host not in url.netloc or url.path.lower().endswith(_SKIP_SUFFIXES):
            continue
        method = request["method"]
        post = request.get("postData") or {}
        mime = post.get("mimeType", "")
        query = ", ".join(sorted({q["name"] for q in request.get("queryString", [])}))
        response = entry.get("response") or {}
        content = response.get("content") or {}
        sent = _keys(post.get("text"), mime)
        got = _keys(content.get("text"), content.get("mimeType", ""))
        csrf = [h["name"] for h in request.get("headers", []) if "csrf" in h["name"].lower()]
        parts = [f"{method} {url.netloc}{url.path}"]
        if query:
            parts.append(f"query: {query}")
        if sent:
            parts.append(f"{mime.split(';')[0]}: {sent}")
        if csrf:
            parts.append(f"headers: {', '.join(csrf)}")
        parts.append(f"→ {response.get('status')} {got}".rstrip())
        lines.append("  ".join(parts))
    return lines
