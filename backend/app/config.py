"""Environment-backed settings for local and containerized runs."""

from dataclasses import dataclass
import os
from pathlib import Path


def _load_local_env_file() -> None:
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        key, value = entry.split("=", maxsplit=1)
        value = value.strip().strip("\"'")
        os.environ.setdefault(key.strip(), value)


_load_local_env_file()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/notebooklm",
    )
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    generation_model: str = os.getenv("GENERATION_MODEL", "gemma2:2b")
    model_provider: str = os.getenv("MODEL_PROVIDER", "ollama").lower()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    max_generation_attempts: int = int(os.getenv("MAX_GENERATION_ATTEMPTS", "2"))
    retrieval_candidate_limit: int = int(os.getenv("RETRIEVAL_CANDIDATE_LIMIT", "20"))
    retrieval_result_limit: int = int(os.getenv("RETRIEVAL_RESULT_LIMIT", "3"))
    prompt_version: str = os.getenv("PROMPT_VERSION", "grounded-v2")


settings = Settings()
