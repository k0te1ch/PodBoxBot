from pydantic import BaseModel, Field, field_validator


class UploadEvent(BaseModel):
    event_type: str = Field(..., description="Тип события: request | progress | result")
    file_name: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    metadata: dict[str, str] | None = Field(None, description="Произвольные метаданные о файле")

    bytes_uploaded: int | None = Field(None, ge=0)
    total_bytes: int | None = Field(None, ge=0)
    progress: float | None = Field(None, ge=0.0, le=1.0)
    transfer_speed: float | None = Field(None, ge=0.0, description="Байт/сек")
    status: str | None = Field(None, description="Текущий статус загрузки")
    error: str | None = Field(None, description="Описание ошибки, если есть")

    message_id: str | None = Field(None, description="ID сообщения, если применимо")
    chat_id: str | None = Field(None, description="ID чата, если применимо")

    type_episode: str | None = Field(
        None, description="main | aftershow — определяет paywall для платных publisher'ов"
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        allowed = {"pending", "uploading", "success", "failure"}
        if v not in allowed:
            raise ValueError(f"Invalid status '{v}', must be one of {allowed}")
        return v
