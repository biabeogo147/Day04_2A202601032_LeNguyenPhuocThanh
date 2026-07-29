from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]
VERSION_DIR = ROOT / "version_1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=VERSION_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    app_database_url: str = "sqlite+aiosqlite:///./version_1/storage/app.db"
    checkpoint_database_path: Path = Field(
        default_factory=lambda: VERSION_DIR / "storage" / "checkpoints.db"
    )
    chroma_persist_directory: Path = Field(
        default_factory=lambda: VERSION_DIR / "storage" / "chroma"
    )
    dataset_path: Path = Field(
        default_factory=lambda: ROOT / "shared_data" / "DataTPCN.csv"
    )
    llm_timeout_seconds: float = 60.0
    tool_timeout_seconds: float = 10.0

    def resolved_path(self, value: Path) -> Path:
        return value if value.is_absolute() else (ROOT / value).resolve()
