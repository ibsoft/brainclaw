from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _safe_project_path(value: str, default_name: str) -> Path:
    raw = Path(value or default_name)
    if not raw.is_absolute():
        raw = BASE_DIR / raw
    resolved = raw.resolve()
    project_root = BASE_DIR.resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"path must stay inside project directory: {resolved}") from exc
    return resolved


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    app_name: str = "BrainClaw"
    host: str = "127.0.0.1"
    port: int = 8757
    log_level: str = "INFO"

    memory_api_key: Optional[str] = Field(default=None, alias="MEMORY_API_KEY")
    allow_missing_api_key: bool = Field(default=False, alias="ALLOW_MISSING_API_KEY")

    data_dir: Path = Field(default=BASE_DIR / "data", alias="DATA_DIR")
    sqlite_path: Path = Field(default=BASE_DIR / "data" / "memory.sqlite3", alias="SQLITE_PATH")
    faiss_index_path: Path = Field(default=BASE_DIR / "data" / "faiss.index", alias="FAISS_INDEX_PATH")
    id_map_path: Path = Field(default=BASE_DIR / "data" / "id_map.json", alias="ID_MAP_PATH")
    upload_dir: Path = Field(default=BASE_DIR / "data" / "uploads", alias="UPLOAD_DIR")

    embedding_model_name: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL_NAME")
    embedding_dimension: int = Field(default=384, alias="EMBEDDING_DIMENSION")

    max_content_chars: int = Field(default=100_000, alias="MAX_CONTENT_CHARS")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")
    max_query_chars: int = Field(default=4_000, alias="MAX_QUERY_CHARS")
    max_tag_chars: int = Field(default=64, alias="MAX_TAG_CHARS")
    max_tags: int = Field(default=32, alias="MAX_TAGS")
    max_top_k: int = Field(default=50, alias="MAX_TOP_K")
    chunk_size_chars: int = Field(default=1_200, alias="CHUNK_SIZE_CHARS")
    chunk_overlap_chars: int = Field(default=160, alias="CHUNK_OVERLAP_CHARS")

    @field_validator("data_dir", mode="before")
    @classmethod
    def validate_data_dir(cls, value: str | Path) -> Path:
        return _safe_project_path(str(value), "data")

    @field_validator("sqlite_path", mode="before")
    @classmethod
    def validate_sqlite_path(cls, value: str | Path) -> Path:
        return _safe_project_path(str(value), "data/memory.sqlite3")

    @field_validator("faiss_index_path", mode="before")
    @classmethod
    def validate_faiss_path(cls, value: str | Path) -> Path:
        return _safe_project_path(str(value), "data/faiss.index")

    @field_validator("id_map_path", mode="before")
    @classmethod
    def validate_id_map_path(cls, value: str | Path) -> Path:
        return _safe_project_path(str(value), "data/id_map.json")

    @field_validator("upload_dir", mode="before")
    @classmethod
    def validate_upload_dir(cls, value: str | Path) -> Path:
        return _safe_project_path(str(value), "data/uploads")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    settings.faiss_index_path.parent.mkdir(parents=True, exist_ok=True)
    settings.id_map_path.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings
