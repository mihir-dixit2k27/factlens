"""FactLens backend application configuration."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://factlens:factlens@localhost:5432/factlens"

    # LLM
    llm_provider: Literal["gemini", "openai", "mock"] = "gemini"
    gemini_api_key: str = ""
    openai_api_key: str = ""

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Upload
    max_upload_size_mb: int = 100

    # Data paths
    data_dir: Path = Path("./data")
    incoming_dir: Path = Path("./data/incoming")
    processed_dir: Path = Path("./data/processed")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Comma-separated origins — JSON array also accepted
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    def get_cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated or JSON-array string."""
        import json
        raw = self.cors_origins.strip()
        if raw.startswith("["):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        return [o.strip() for o in raw.split(",") if o.strip()]

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # Processing
    chunk_max_tokens: int = 512
    chunk_overlap_tokens: int = 64
    sparse_text_threshold: float = 0.1  # chars per pixel — below this triggers fallback
    min_fact_confidence: float = 0.4
    embedding_batch_size: int = 64

    # Reconciliation thresholds (fact-type dependent)
    corroboration_threshold_monetary: float = 0.05   # 5% relative diff
    corroboration_threshold_percentage: float = 0.02  # 2 percentage points absolute diff
    corroboration_threshold_count: float = 0.10       # 10% relative diff
    corroboration_threshold_default: float = 0.05


    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
