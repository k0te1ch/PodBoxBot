import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class MetricsMiddleware(BaseMiddleware):
    """
    Middleware для сбора и сохранения метрик по вызовам handler'ов
    """

    def __init__(self, metrics_path: Path = Path("metrics.json")) -> None:
        self.call_counts = defaultdict(int)
        self.metrics_path = metrics_path

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        handler_info = data.get("handler")
        handler_name = handler_info.callback.__name__ if handler_info else "unknown"

        self.call_counts[handler_name] += 1
        self._save_metrics()

        return await handler(event, data)

    def _save_metrics(self) -> None:
        try:
            with self.metrics_path.open("w", encoding="utf-8") as f:
                json.dump(self.call_counts, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[MetricsMiddleware] Error saving metrics: {e}")

    def get_metrics(self) -> dict[str, int]:
        return dict(self.call_counts)
