from pydantic import BaseModel


class UploadPayload(BaseModel):
    file_name: str
    path: str
    username: str
    metadata: dict[str, str] | None = None
