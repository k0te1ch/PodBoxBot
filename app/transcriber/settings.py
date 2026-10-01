"""Настройки сервиса расшифровки: из окружения и общего ``.env`` проекта."""

from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    REDIS_URL: str | None = None
    REDIS_PASSWORD: str | None = None
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    FILES_PATH: str = "files"

    WHISPER_MODEL: str = "small"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_CPU_THREADS: int = 2
    WHISPER_BEAM_SIZE: int = 1
    WHISPER_LANGUAGE: str = "ru"
    WHISPER_MODELS_DIR: str | None = None
    # Аудио расшифровывается кусками такой длины: память не растёт с длиной выпуска.
    WHISPER_CHUNK_MINUTES: float = 10.0
    # Дольше одна расшифровка идти не должна: зависший процесс не держит очередь.
    WHISPER_TIMEOUT_HOURS: float = 6.0

    @property
    def redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        password = f":{quote(self.REDIS_PASSWORD, safe='')}@" if self.REDIS_PASSWORD else ""
        return f"redis://{password}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
