from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NODEPASS_", env_file=".env", extra="ignore")

    environment: Literal["development", "production"] = "development"
    database_url: str = "postgresql+psycopg://nodepass:nodepass-local-only@127.0.0.1:55432/nodepass"
    session_secret: SecretStr
    credentials_key: SecretStr | None = None
    session_hours: int = 8
    cookie_secure: bool = True
    web_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        secret = self.session_secret.get_secret_value()
        if len(secret) < 32 or secret == "replace-with-generated-secret":
            raise ValueError("Generate a session secret with: python -m app.cli init-env")
        if not 1 <= self.session_hours <= 24:
            raise ValueError("Session lifetime must be between 1 and 24 hours")
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("Production sessions require secure cookies")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
