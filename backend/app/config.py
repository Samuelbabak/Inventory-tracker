from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="INVENTORY_",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+pysqlite:///./inventory-dev.db"
    auth_provider: Literal["local", "oidc"] = "local"
    session_cookie_name: str = "haynes_session"
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    secure_cookies: bool = False
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    spectrum_adapter: Literal["fake", "disabled"] = "fake"
    worker_poll_seconds: float = Field(default=2, ge=0.1, le=60)

    @model_validator(mode="after")
    def prevent_local_auth_in_production(self) -> "Settings":
        if self.environment == "production" and self.auth_provider == "local":
            raise ValueError("Local authentication cannot be enabled in production")
        if self.environment == "production" and not self.secure_cookies:
            raise ValueError("Secure cookies are required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
