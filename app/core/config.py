from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = Field(default="local")
    database_url: str = Field(default="postgresql+asyncpg://hotel:hotel@localhost:5432/hotel")

    jwt_secret: str = Field(default="dev-secret-change-me")
    jwt_algorithm: str = Field(default="HS256")
    access_token_minutes: int = Field(default=15)
    refresh_token_days: int = Field(default=7)

    stripe_api_key: str = Field(default="sk_test_placeholder")
    stripe_webhook_secret: str = Field(default="whsec_placeholder")

    reservation_hold_minutes: int = Field(default=15)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
