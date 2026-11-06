"""Application settings loaded from environment variables or .env."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

JWT_SECRET_PLACEHOLDER = "replace-with-a-long-random-string"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    # hide_input_in_errors keeps connection strings and secrets out of tracebacks.
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # A Literal means a typo like APP_ENV=devv stops startup instead of quietly
    # selecting the main database.
    app_env: Literal["dev", "prod"] = "prod"
    database_url: str
    dev_database_url: str | None = None
    jwt_secret: str
    jwt_expire_minutes: int = Field(default=60, gt=0)
    turn_near_position: int = Field(default=3, gt=0)

    @field_validator("jwt_secret")
    @classmethod
    def reject_weak_jwt_secret(cls, value: str) -> str:
        if value == JWT_SECRET_PLACEHOLDER:
            raise ValueError("JWT_SECRET is still the placeholder from .env.example")
        if len(value) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters")
        return value

    @model_validator(mode="after")
    def require_separate_dev_database(self) -> Self:
        """Stop dev mode from ever falling back to the main database."""
        if self.app_env != "dev":
            return self
        if not self.dev_database_url:
            raise ValueError("APP_ENV=dev requires DEV_DATABASE_URL to be set")
        if self.dev_database_url == self.database_url:
            raise ValueError("DEV_DATABASE_URL must differ from DATABASE_URL")
        return self

    @property
    def active_database_url(self) -> str:
        """The connection string selected by APP_ENV."""
        if self.app_env == "dev":
            return self.dev_database_url
        return self.database_url

    @property
    def database_target(self) -> str:
        """Describe the active database without revealing the URL."""
        name = "dev" if self.app_env == "dev" else "main"
        host = make_url(self.active_database_url).host or ""
        host_type = "pooled" if "-pooler" in host else "direct"
        return f"{name} ({host_type} host)"


settings = Settings()
