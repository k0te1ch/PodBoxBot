"""Shared scaffolding for podcast publishers.

Каждый publisher — это Kafka-consumer, который слушает `<name>.upload`,
выполняет платформо-специфичную публикацию и шлёт результат в
`<name>.result`. Общий код (Kafka обвязка, метрики, лайфсайкл, паттерн
обработки ошибок) живёт здесь, чтобы FTP/WordPress/VK/Boosty/Patreon/
sponsr делились им вместо копипасты.
"""

from .base import BasePublisher
from .metrics import PublisherMetrics

__all__ = ["BasePublisher", "PublisherMetrics"]
