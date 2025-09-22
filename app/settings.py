from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    # Provider selector: openai | anthropic | groq
    MODEL_PROVIDER: str = Field(default="openai")

    # Model names (override in .env if you like)
    OPENAI_MODEL: str = Field(default="gpt-4o-mini")
    ANTHROPIC_MODEL: str = Field(default="claude-3-5-sonnet-latest")
    GROQ_MODEL: str = Field(default="llama-3.1-70b-versatile")
    DEEPSEEK_MODEL: str = Field(default="deepseek-reasoner")

    # API keys (optional depending on provider you use)
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    DEEPSEEK_API_KEY: str | None = None

    # Optional custom base URLs
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com")

    # Tools & data
    TAVILY_API_KEY: str | None = None

    # Supabase
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # Tuning & runtime
    TEMPERATURE: float = Field(default=0.2)
    MAX_TOKENS: int = Field(default=800)
    REQUEST_TIMEOUT_S: float = Field(default=60)

    @field_validator("TEMPERATURE")
    @classmethod
    def _clamp_temp(cls, v: float) -> float:
        return max(0.0, min(2.0, v))

    @field_validator("MAX_TOKENS")
    @classmethod
    def _min_tokens(cls, v: int) -> int:
        return max(1, v)

# Pydantic v2 settings config
    # Resolve repo root (app/ is directly under repo root)
    _REPO_ROOT = Path(__file__).resolve().parent.parent
    model_config = SettingsConfigDict(env_file=str(_REPO_ROOT / ".env"), case_sensitive=True, extra="ignore")


settings = Settings()

