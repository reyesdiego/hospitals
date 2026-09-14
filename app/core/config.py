from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Hospital Internment API"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    postgres_host: str = "localhost"
    postgres_port: int = 5434
    postgres_db: str = "hospital"
    postgres_user: str = "hospital"
    postgres_password: str = "hospital_dev_password"
    db_echo: bool = False

    @computed_field
    @property
    def database_url(self) -> str:
        return (f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}")

@lru_cache
def get_settings() -> Settings:
    return Settings()
settings = get_settings()
