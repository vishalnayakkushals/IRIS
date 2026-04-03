from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = "/app/data/store_registry.db"
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
    def db_path_obj(self) -> Path:
        return Path(self.db_path)

    @property
    def data_root_obj(self) -> Path:
        return Path(self.data_root)


@lru_cache
def get_settings() -> Settings:
    return Settings()
