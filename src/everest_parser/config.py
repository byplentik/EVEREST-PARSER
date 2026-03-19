"""Настройки приложения."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки выполнения, загружаемые из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://everest:everest@localhost:5432/everest_parser",
        alias="DATABASE_URL",
    )
    http_timeout_seconds: int = Field(default=30, alias="HTTP_TIMEOUT_SECONDS")
    http_verify_ssl: bool = Field(default=True, alias="HTTP_VERIFY_SSL")
    http_proxy_url: str | None = Field(default=None, alias="HTTP_PROXY_URL")
    browser_proxy_url: str | None = Field(default=None, alias="BROWSER_PROXY_URL")
    request_delay_seconds: float = Field(default=2.0, alias="REQUEST_DELAY_SECONDS")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")

    @field_validator("http_proxy_url", "browser_proxy_url", mode="before")
    @classmethod
    def normalize_empty_string_fields(cls, value: object) -> object:
        """Преобразовать пустые строковые значения в `None`."""

        if value == "":
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Вернуть кэшированный объект настроек приложения."""

    return Settings()
