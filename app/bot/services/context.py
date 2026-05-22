import inspect
import json
from pathlib import Path
from typing import Any

from loguru import logger

from services.none_module import _NoneModule

LOCALES_DIR = Path(__file__).parent.parent / "locales"


def _parse_ftl_value(value: str) -> Any:
    trimmed = value.strip()
    if trimmed.startswith('"') and trimmed.endswith('"') and len(trimmed) >= 2:
        trimmed = trimmed[1:-1]
    if trimmed.startswith("[") or trimmed.startswith("{"):
        try:
            return json.loads(trimmed)
        except json.JSONDecodeError:
            pass
    return trimmed


def _collect_multiline(lines: list[str], index: int, first_line: str | None = None) -> tuple[str, int]:
    content_lines: list[str] = []
    if first_line is not None:
        content_lines.append(first_line)

    while index < len(lines):
        line = lines[index].rstrip("\n")
        if not line or line[0] not in {" ", "\t"}:
            break
        content_lines.append(line.lstrip(" \t"))
        index += 1

    return "\n".join(content_lines), index


def _parse_ftl_object(lines: list[str], index: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}

    while index < len(lines):
        raw_line = lines[index].rstrip("\n")
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            index += 1
            continue
        if stripped == "}":
            return result, index + 1
        if "=" not in raw_line or not stripped.startswith("."):
            raise ValueError(f"Invalid FTL object attribute at line: {raw_line}")

        attr, raw_value = raw_line.split("=", 1)
        attr_name = attr.strip()[1:]
        raw_value = raw_value.lstrip()

        if raw_value == "|" or raw_value.startswith("|"):
            first_line = raw_value[1:] if raw_value.startswith("|") else None
            value, index = _collect_multiline(lines, index + 1, first_line)
        else:
            value = _parse_ftl_value(raw_value)
            index += 1

        result[attr_name] = value

    raise ValueError("Unterminated FTL object")


def _parse_ftl_file(locale_file: Path) -> dict[str, Any]:
    with open(locale_file, encoding="utf-8") as f:
        lines = f.readlines()

    translations: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        raw_line = lines[index].rstrip("\n")
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            index += 1
            continue
        if "=" not in raw_line:
            raise ValueError(f"Invalid FTL line: {raw_line}")

        key, raw_value = raw_line.split("=", 1)
        key = key.strip()
        raw_value = raw_value.lstrip()

        if raw_value == "{":
            value, index = _parse_ftl_object(lines, index + 1)
        elif raw_value == "|" or raw_value.startswith("|"):
            first_line = raw_value[1:] if raw_value.startswith("|") else None
            value, index = _collect_multiline(lines, index + 1, first_line)
        else:
            value = _parse_ftl_value(raw_value)
            index += 1

        translations[key] = value

    return translations


class _LangWrapper:
    def __init__(self, data: dict) -> None:
        self._data = data

    def __getitem__(self, name: str) -> Any:
        value = self._data.get(name)
        if value is None:
            return f'"{name}" is not defined.'
        if isinstance(value, str):
            frame = inspect.currentframe()
            try:
                if frame and frame.f_back and frame.f_back.f_locals:
                    value = value.format_map(frame.f_back.f_locals)
            finally:
                del frame
        return value

    def __getattr__(self, name: str) -> Any:
        return self[name]


class I18nContext:
    def __init__(self, locales_dir: Path = LOCALES_DIR) -> None:
        self._translations: dict[str, dict] = {}
        self._load(locales_dir)

    def _load(self, locales_dir: Path) -> None:
        for locale_file in sorted(locales_dir.glob("*.ftl")):
            lang = locale_file.stem
            self._translations[lang] = _parse_ftl_file(locale_file)
            logger.debug(f"Locale loaded: {lang}")

    def __getitem__(self, lang: str) -> _LangWrapper:
        data = self._translations.get(lang) or self._translations.get("ru", {})
        return _LangWrapper(data)


def _get_context_obj() -> I18nContext | _NoneModule:
    if not LOCALES_DIR.exists():
        logger.warning(f"Locales directory not found: {LOCALES_DIR}")
        return _NoneModule("text", "LOCALES_DIR")
    context = I18nContext(LOCALES_DIR)
    logger.debug("I18n context loaded")
    return context
