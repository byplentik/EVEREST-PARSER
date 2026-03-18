"""Настройки приложения."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Настройки выполнения, загружаемые из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="everest-parser", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    postgres_db: str = Field(default="everest_parser", alias="POSTGRES_DB")
    postgres_user: str = Field(default="everest", alias="POSTGRES_USER")
    postgres_password: str = Field(default="everest", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    database_url: str = Field(
        default="postgresql+psycopg://everest:everest@localhost:5432/everest_parser",
        alias="DATABASE_URL",
    )

    uc_headless: bool = Field(default=True, alias="UC_HEADLESS")
    uc_enable_cdp_events: bool = Field(default=True, alias="UC_ENABLE_CDP_EVENTS")
    uc_version_main: int | None = Field(default=None, alias="UC_VERSION_MAIN")
    uc_browser_executable_path: str | None = Field(default=None, alias="UC_BROWSER_EXECUTABLE_PATH")
    uc_user_data_dir: str | None = Field(default=None, alias="UC_USER_DATA_DIR")
    uc_page_load_timeout_seconds: int = Field(default=60, alias="UC_PAGE_LOAD_TIMEOUT_SECONDS")

    http_timeout_seconds: int = Field(default=30, alias="HTTP_TIMEOUT_SECONDS")
    http_verify_ssl: bool = Field(default=True, alias="HTTP_VERIFY_SSL")
    http_proxy_url: str | None = Field(default=None, alias="HTTP_PROXY_URL")
    browser_proxy_url: str | None = Field(default=None, alias="BROWSER_PROXY_URL")
    default_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        alias="DEFAULT_USER_AGENT",
    )

    request_delay_seconds: float = Field(default=2.0, alias="REQUEST_DELAY_SECONDS")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")

    @field_validator(
        "uc_version_main",
        mode="before",
    )
    @classmethod
    def normalize_empty_integer_fields(cls, value: object) -> object:
        """Преобразовать пустые строковые значения в None для необязательных чисел."""

        if value == "":
            return None
        return value

    @field_validator(
        "uc_browser_executable_path",
        "uc_user_data_dir",
        "http_proxy_url",
        "browser_proxy_url",
        mode="before",
    )
    @classmethod
    def normalize_empty_string_fields(cls, value: object) -> object:
        """Преобразовать пустые строковые значения в None для необязательных строк."""

        if value == "":
            return None
        return value

    def public_summary(self) -> dict[str, object]:
        """Вернуть безопасную для вывода сводку по конфигурации."""

        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "log_level": self.log_level,
            "database_url": self.masked_database_url(),
            "uc_headless": self.uc_headless,
            "uc_enable_cdp_events": self.uc_enable_cdp_events,
            "uc_version_main": self.uc_version_main,
            "uc_browser_executable_path": self.uc_browser_executable_path,
            "http_timeout_seconds": self.http_timeout_seconds,
            "http_verify_ssl": self.http_verify_ssl,
            "http_proxy_configured": bool(self.http_proxy_url),
            "browser_proxy_configured": bool(self.browser_proxy_url),
            "request_delay_seconds": self.request_delay_seconds,
            "max_retries": self.max_retries,
        }

    def masked_database_url(self) -> str:
        """Вернуть URL подключения к БД без пароля."""

        return make_url(self.database_url).render_as_string(hide_password=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Вернуть кэшированный объект настроек приложения."""

    return Settings()
