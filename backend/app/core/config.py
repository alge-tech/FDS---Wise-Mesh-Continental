from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Names match the PRD's environment-variable table."""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://mesh_app:mesh_app@localhost:5434/mesh"
    migration_database_url: str = "postgresql+psycopg://mesh:mesh@localhost:5434/mesh"
    jwt_secret: str
    session_hours: int = 8
    demo_mode: bool = True
    netting_time_budget_ms: int = 2000
    max_recomputes: int = 2
    standard_rate_bps: int = 52
    fee_share_bps: int = 2500
    dust_threshold_minor: int = 100
    fx_lock_minutes: int = 30
    algo_version: str = "net-0.1.0"
    price_version: str = "2026-10-demo"
    rules_version: str = "rules-0.1.0"

    allowed_origins: list[str] = ["http://localhost:3010", "http://127.0.0.1:3010"]
    cookie_name: str = "mesh_session"
    cookie_secure: bool = False
    csv_max_bytes: int = 5 * 1024 * 1024
    csv_max_rows: int = 10_000
    worker_enabled: bool = True
    worker_poll_seconds: float = 1.0
    log_level: str = "INFO"
    demo_password: str = "mesh-demo-2026"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # jwt_secret comes from the environment
