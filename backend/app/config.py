from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_url: str = "postgresql+asyncpg://iris_user:password@localhost/iris_db"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = "change_me_in_env"
    jwt_expire_days: int = 14
    store_id: str = "TEST_STORE_D07"
    data_root: str = "/app/data"
    google_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    onfly_source_url: str = ""
    yolo_conf: float = 0.18
    max_images: int = 100

    model_config = {"env_prefix": "", "case_sensitive": False}

    @property
    def get_db_url(self) -> str:
        return self.postgres_url

    @property
    def data_root_obj(self) -> Path:
        configured = Path(self.data_root)
        if configured.as_posix() == "/app/data":
            return Path(__file__).resolve().parents[2] / "data"
        if configured.is_absolute():
            return configured
        return (Path(__file__).resolve().parents[2] / configured).resolve()

    @property
    def db_path_obj(self) -> Path:
        return self.data_root_obj / "store_registry.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
