import inspect
import json
from pathlib import Path
from typing import Any

from loguru import logger

from services.none_module import _NoneModule

LOCALES_DIR = Path(__file__).parent.parent / "locales"


class _LangWrapper:
    def __init__(self, data: dict) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
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


class I18nContext:
    def __init__(self, locales_dir: Path = LOCALES_DIR) -> None:
        self._translations: dict[str, dict] = {}
        self._load(locales_dir)

    def _load(self, locales_dir: Path) -> None:
        for locale_file in sorted(locales_dir.glob("*.json")):
            lang = locale_file.stem
            with open(locale_file, encoding="utf-8") as f:
                self._translations[lang] = json.load(f)
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
