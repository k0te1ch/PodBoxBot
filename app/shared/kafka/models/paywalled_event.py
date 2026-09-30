"""События публикации послешоу на платных площадках VK Donut, Patreon, Sponsr.

Поля те же, что у :class:`BoostyEvent`: бот собирает одно и то же послешоу, а
площадки различаются только тем, как ставят замок. У каждой площадки своя
модель и свой .avsc, чтобы схемы в Schema Registry эволюционировали
независимо.
"""

from pydantic import BaseModel, Field, field_validator


class PaywalledPostEvent(BaseModel):
    event_type: str = Field(..., description="Тип события: request | result")
    username: str = Field(..., min_length=1)
    status: str | None = Field(None, description="pending | success | failure | retrying")
    error: str | None = Field(None, description="Описание ошибки")
    metadata: dict[str, str] | None = Field(None, description="Подробности попытки: stage, attempt, attempts, url")
    chat_id: str | None = Field(None)
    message_id: str | None = Field(None)

    path: str | None = Field(None, description="Путь к mp3 на общем томе files")
    number: str = Field(..., description="Номер эпизода")
    title: str = Field(...)
    comment: str = Field(..., description="Тело поста / описание эпизода")
    chapters: list[list[str]] = Field(default_factory=list, description="Таймлайн [[time, name], ...]")
    tags: list[str] = Field(default_factory=list)

    type_episode: str | None = Field(None, description="main | aftershow")
    paywall_tier: str | None = Field(None, description="Уровень подписки площадки; приоритетнее type_episode")

    post_id: str | None = Field(None, description="ID созданного поста (в success-result)")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        allowed = {"pending", "success", "failure", "retrying"}
        if v not in allowed:
            raise ValueError(f"Invalid status '{v}', must be one of {allowed}")
        return v


class VkEvent(PaywalledPostEvent):
    """Пост для донов VK Donut на стене сообщества."""


class PatreonEvent(PaywalledPostEvent):
    """Пост для патронов Patreon."""


class SponsrEvent(PaywalledPostEvent):
    """Пост для подписчиков Sponsr."""
