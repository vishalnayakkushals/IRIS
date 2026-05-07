from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


_INSECURE_JWT_DEFAULT = "change_me_in_env"


class Settings(BaseSettings):
    postgres_url: str = "postgresql+asyncpg://iris_user:iris_password@127.0.0.1/iris_db"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = _INSECURE_JWT_DEFAULT
    jwt_expire_days: int = 14
    store_id: str = ""
    data_root: str = "/app/data"
    google_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    onfly_source_url: str = ""
    yolo_conf: float = 0.20
    max_images: int = 10000
    
    # Storage Settings (S3 vs Local/Drive)
    enable_s3_storage: bool = False
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket_name: str = ""

    # "production" triggers hard checks (insecure JWT → startup error, etc.)
    environment: str = "development"

    # Comma-separated allowed CORS origins; defaults cover local dev only
    cors_origins: str = "http://localhost:3000,http://localhost:8767,http://127.0.0.1:8767"

    model_config = {"env_prefix": "", "case_sensitive": False, "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def jwt_is_insecure(self) -> bool:
        return self.jwt_secret == _INSECURE_JWT_DEFAULT

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
