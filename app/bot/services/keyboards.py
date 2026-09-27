import importlib
import os
from typing import Any

from loguru import logger

from config import KEYBOARDS, KEYBOARDS_DIR, KEYBOARDS_PATH


class _Keyboards:
    """Доступ к модулю клавиатур по атрибуту и по ключу: ``kb["ru"].cancel``.

    Вложенные классы (``_Lang`` на язык) заворачиваются в тот же адаптер.
    Неизвестное имя поднимает ``AttributeError``, а не возвращает строку-заглушку,
    которая раньше молча уходила в ``reply_markup``.
    """

    def __init__(self, keyboard_obj: Any) -> None:
        self._keyboard_obj = keyboard_obj

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._keyboard_obj, name)
        return _Keyboards(value) if isinstance(value, type) else value

    def __getitem__(self, name: str) -> Any:
        return self.__getattr__(name)


@logger.catch
def _get_keyboards_obj() -> dict:
    keyboards = [m[:-3] for m in os.listdir(KEYBOARDS_PATH) if m.endswith(".py") and m[:-3] in KEYBOARDS]
    logger.opt(colors=True).debug(f"Loading <y>{len(keyboards)}</y> keyboards")
    tmp = {}
    for keyboard in keyboards:
        tmp[keyboard] = _Keyboards(importlib.import_module(f"{KEYBOARDS_DIR}.{keyboard}"))
        logger.opt(colors=True).debug(f"Loading <y>{keyboard}</y>...   <light-green>loaded</light-green>")
    logger.opt(colors=True).debug("Keyboards loaded")
    return tmp
