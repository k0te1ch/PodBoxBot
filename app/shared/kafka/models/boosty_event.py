from pydantic import BaseModel, Field, field_validator


class BoostyEvent(BaseModel):
    """Событие публикации поста на Boosty.

    Мирроринг WordPressEvent: своя модель + .avsc + топик. Несёт всё, что
    нужно для создания поста через internal-API Boosty (см. спайк
    `.planning/spikes/boosty-sponsr-feasibility.md`):

    * `title`/`comment` — заголовок и тело поста;
    * `type_episode`/`paywall_tier` — определяют tier (free vs paid level),
      см. `BasePublisher.is_paywalled`;
    * `post_id` — id созданного поста (заполняется в success-result для
      идемпотентности/дедупа на стороне бота).
    """

    event_type: str = Field(..., description="Тип события: request | result")
    username: str = Field(..., min_length=1)
    status: str | None = Field(None, description="pending | success | failure")
    error: str | None = Field(None, description="Описание ошибки")
    chat_id: str | None = Field(None)
    message_id: str | None = Field(None)

    # Данные поста
    number: str = Field(..., description="Номер эпизода")
    title: str = Field(...)
    comment: str = Field(..., description="Тело поста / описание эпизода")
    chapters: list[list[str]] = Field(default_factory=list, description="Таймлайн [[time, name], ...]")
    tags: list[str] = Field(default_factory=list)

    # Paywall / tier
    type_episode: str | None = Field(
        None, description="main | aftershow — определяет paywall для платных publisher'ов"
    )
    paywall_tier: str | None = Field(
        None,
        description=(
            "Явный tier: имя уровня подписки Boosty или его id. Приоритетнее "
            "type_episode. None → используется дефолтный уровень из конфига "
            "(aftershow → платный, иначе → бесплатный)."
        ),
    )

    # Заполняется в success-result
    post_id: str | None = Field(None, description="ID созданного поста на Boosty")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        allowed = {"pending", "success", "failure"}
        if v not in allowed:
            raise ValueError(f"Invalid status '{v}', must be one of {allowed}")
        return v
