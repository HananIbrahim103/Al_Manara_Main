import json
from functools import lru_cache

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # Found wherever the app is started from: the repository root's .env, then backend/.env (which wins).
    # Real environment variables win over both.
    model_config = SettingsConfigDict(env_file=(_BACKEND.parent / ".env", _BACKEND / ".env"), extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql://localhost:5432/tdra_gov"

    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 720

    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    cors_origin_regex: str = ""

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    agent_model: str = "google/gemini-2.5-flash"
    judge_model: str = "google/gemini-2.5-flash"
    llm_mode: str = "mock"
    model_id_overrides: str = ""

    @property
    def sqlalchemy_url(self) -> str:
        """Render gives postgres:// or postgresql://; SQLAlchemy needs the driver named."""
        url = self.database_url
        for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        """The configured origins, plus the local frontend ports, so a local copy of the frontend can always reach this API.
        Safe because sign-in is a bearer token in a header, never a cookie."""
        configured = [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]
        local = [f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (3000, 5173)]
        return configured + [o for o in local if o not in configured]

    @property
    def model_overrides(self) -> dict[str, str]:
        return json.loads(self.model_id_overrides) if self.model_id_overrides.strip() else {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
