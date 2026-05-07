from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://pharmasignal:pharmasignal_secret@localhost:5432/pharmasignal"
    DATABASE_URL_SYNC: str = "postgresql://pharmasignal:pharmasignal_secret@localhost:5432/pharmasignal"

    @model_validator(mode="after")
    def fix_db_urls(self) -> "Settings":
        # Normalise legacy postgres:// scheme (used by some Railway addons)
        for attr in ("DATABASE_URL", "DATABASE_URL_SYNC"):
            val = getattr(self, attr)
            if val.startswith("postgres://"):
                setattr(self, attr, val.replace("postgres://", "postgresql://", 1))

        # Ensure async driver for SQLAlchemy async engine
        if not self.DATABASE_URL.startswith("postgresql+asyncpg://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Ensure sync URL has no asyncpg
        self.DATABASE_URL_SYNC = self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
        return self

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Reddit
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "PharmaSignal/1.0"

    # Twitter/X
    TWITTER_API_KEY: str = ""

    # Gemini (replaces Anthropic)
    GEMINI_API_KEY: str = ""

    # Anthropic (kept for backward compat — not used)
    ANTHROPIC_API_KEY: str = ""

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change_me"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost", "http://localhost:80", "https://*.railway.app"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
