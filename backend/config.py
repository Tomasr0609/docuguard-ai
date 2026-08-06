from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # LLM
    llm_provider: str = "ollama"  # "ollama" | "anthropic" | "gemini"
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"
    daily_request_limit: int = 150  # 0 means unlimited
    upload_cooldown_seconds: int = 60  # 0 disables the upload cooldown

    # Database
    database_url: str = "sqlite+aiosqlite:///./docuguard.db"

    # Vector store
    chroma_db_path: str = "./chroma_db"

    # App
    log_level: str = "INFO"
    max_file_size_mb: int = 50

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


settings = Settings()
