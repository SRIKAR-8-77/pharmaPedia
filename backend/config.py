from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://pharmasignal:pharmasignal_secret@localhost:5432/pharmasignal"
    DATABASE_URL_SYNC: str = "postgresql://pharmasignal:pharmasignal_secret@localhost:5432/pharmasignal"

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
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost", "http://localhost:80"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
