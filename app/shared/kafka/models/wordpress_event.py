from pydantic import BaseModel, Field, field_validator


class WordPressEvent(BaseModel):
    event_type: str = Field(..., description="Тип события: request | result")
    username: str = Field(..., min_length=1)
    status: str | None = Field(None, description="pending | success | failure")
    error: str | None = Field(None, description="Описание ошибки")
    chat_id: str | None = Field(None)
    message_id: str | None = Field(None)

    # Данные поста
    number: str = Field(..., description="Номер эпизода")
    title: str = Field(...)
    comment: str = Field(..., description="Описание эпизода")
    chapters: list[list[str]] = Field(default_factory=list, description="[[time, name], ...]")
    tags: list[str] = Field(default_factory=list)
    slug: str = Field(..., description="Slug файла")
    duration: int | None = Field(None, description="Длительность в секундах")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        allowed = {"pending", "success", "failure"}
        if v not in allowed:
            raise ValueError(f"Invalid status '{v}', must be one of {allowed}")
        return v
