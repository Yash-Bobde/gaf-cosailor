"""Application configuration loaded from environment variables and .env file.

Settings uses pydantic-settings for automatic env-var validation at startup.
ScraperConfig holds GAF-scraper parameters that are always passed as a
structured object — never hardcoded at call sites.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from dataclasses import dataclass
from typing import Literal

Segment = Literal["residential", "commercial"]
SUPPORTED_DISTANCES = (25, 50, 100)
SUPPORTED_SEGMENTS = ("residential", "commercial")


class Settings(BaseSettings):
    """Environment-sourced API keys, Supabase credentials and pipeline tuning.

    Required fields raise ValidationError at startup. Perplexity does the web
    research; OpenAI does scoring and the call brief. pipeline_concurrency bounds
    how many leads are researched/enriched at once — the main throughput knob,
    limited in practice by the Perplexity and OpenAI accounts' rate limits.
    """
    supabase_url: str
    supabase_key: str
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    perplexity_api_key: str
    # Agent API preset; "fast" is Perplexity's replacement for the retired Sonar model.
    perplexity_preset: str = "fast"
    pipeline_concurrency: int = 8
    # Comma-separated browser origins allowed by CORS (explicit list, no wildcards).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()


@dataclass(frozen=True)
class ScraperConfig:
    """Runtime parameters for a single GAF contractor scrape.

    segment selects the GAF directory (the case study specifies residential).
    distance must be one of the three values GAF supports (25 / 50 / 100 miles).
    limit caps how many contractors are processed — useful for demos and cost control.
    """
    postal_code: str = "10013"
    country_code: str = "us"
    distance: int = 25
    segment: Segment = "residential"
    limit: int | None = None

    def __post_init__(self):
        if self.distance not in SUPPORTED_DISTANCES:
            raise ValueError(f"distance must be 25, 50, or 100. Got: {self.distance}")
        if self.segment not in SUPPORTED_SEGMENTS:
            raise ValueError(f"segment must be 'residential' or 'commercial'. Got: {self.segment}")
        if self.limit is not None and self.limit < 1:
            raise ValueError(f"limit must be a positive integer. Got: {self.limit}")
