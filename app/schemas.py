from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.config import get_settings


def _clean_text(value: str) -> str:
    return " ".join(value.strip().split())


class MemoryAddRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    workspace: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=256)
    memory_type: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("agent_id", "workspace", "source", "memory_type")
    @classmethod
    def normalize_short_text(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, value: str) -> str:
        settings = get_settings()
        if len(value) > settings.max_content_chars:
            raise ValueError(f"content exceeds max length of {settings.max_content_chars} characters")
        return value.strip()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: list[str]) -> list[str]:
        settings = get_settings()
        if len(tags) > settings.max_tags:
            raise ValueError(f"too many tags; max is {settings.max_tags}")
        cleaned: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            normalized = _clean_text(tag).lower()
            if not normalized:
                continue
            if len(normalized) > settings.max_tag_chars:
                raise ValueError(f"tag exceeds max length of {settings.max_tag_chars} characters")
            if normalized not in seen:
                seen.add(normalized)
                cleaned.append(normalized)
        return cleaned


class MemoryUpdateRequest(BaseModel):
    id: int = Field(gt=0)
    agent_id: str = Field(min_length=1, max_length=128)
    workspace: str = Field(min_length=1, max_length=256)
    source: Optional[str] = Field(default=None, min_length=1, max_length=256)
    memory_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    content: Optional[str] = Field(default=None, min_length=1)
    tags: Optional[list[str]] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        settings = get_settings()
        if len(value) > settings.max_content_chars:
            raise ValueError(f"content exceeds max length of {settings.max_content_chars} characters")
        return value.strip()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: Optional[list[str]]) -> Optional[list[str]]:
        if tags is None:
            return None
        return MemoryAddRequest(
            agent_id="validator",
            workspace="validator",
            source="validator",
            memory_type="validator",
            content="validator",
            tags=tags,
        ).tags


class MemorySearchRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    workspace: str = Field(min_length=1, max_length=256)
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1)
    min_score: float = Field(default=0.2, ge=-1.0, le=1.0)
    tags: Optional[list[str]] = None
    memory_type: Optional[str] = Field(default=None, min_length=1, max_length=64)

    @field_validator("query")
    @classmethod
    def validate_query_size(cls, value: str) -> str:
        settings = get_settings()
        if len(value) > settings.max_query_chars:
            raise ValueError(f"query exceeds max length of {settings.max_query_chars} characters")
        return value.strip()

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, value: int) -> int:
        settings = get_settings()
        if value > settings.max_top_k:
            raise ValueError(f"top_k exceeds max value of {settings.max_top_k}")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: Optional[list[str]]) -> Optional[list[str]]:
        if tags is None:
            return None
        return MemoryAddRequest(
            agent_id="validator",
            workspace="validator",
            source="validator",
            memory_type="validator",
            content="validator",
            tags=tags,
        ).tags


class MemoryDeleteRequest(BaseModel):
    id: int = Field(gt=0)
    agent_id: str = Field(min_length=1, max_length=128)
    workspace: str = Field(min_length=1, max_length=256)


class MemoryResponse(BaseModel):
    id: int
    agent_id: str
    workspace: str
    source: str
    memory_type: str
    content: str
    tags: list[str]
    importance: float
    created_at: datetime
    updated_at: datetime
    chunk_count: int


class MemorySearchResult(BaseModel):
    id: int
    chunk_id: int
    score: float
    agent_id: str
    workspace: str
    source: str
    memory_type: str
    content: str
    chunk_text: str
    tags: list[str]
    importance: float
    created_at: datetime
    updated_at: datetime


class FileSearchRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    workspace: str = Field(min_length=1, max_length=256)
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1)
    min_score: float = Field(default=0.2, ge=-1.0, le=1.0)
    file_id: Optional[int] = Field(default=None, gt=0)
    tags: Optional[list[str]] = None

    @field_validator("agent_id", "workspace")
    @classmethod
    def normalize_short_text(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("query")
    @classmethod
    def validate_query_size(cls, value: str) -> str:
        settings = get_settings()
        if len(value) > settings.max_query_chars:
            raise ValueError(f"query exceeds max length of {settings.max_query_chars} characters")
        return value.strip()

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, value: int) -> int:
        settings = get_settings()
        if value > settings.max_top_k:
            raise ValueError(f"top_k exceeds max value of {settings.max_top_k}")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: Optional[list[str]]) -> Optional[list[str]]:
        if tags is None:
            return None
        return MemoryAddRequest(
            agent_id="validator",
            workspace="validator",
            source="validator",
            memory_type="validator",
            content="validator",
            tags=tags,
        ).tags


class FileUploadResponse(BaseModel):
    ok: bool
    file_id: int
    message: str
    sha256: str
    stored_filename: str
    chunks: int
    duplicate: bool = False


class FileSearchResult(BaseModel):
    file_id: int
    file_chunk_id: int
    score: float
    agent_id: str
    workspace: str
    source: str
    original_filename: str
    extension: str
    sha256: str
    size_bytes: int
    chunk_text: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    app: str
    index_vectors: int
    sqlite_path: str
    faiss_index_path: str


class StatusResponse(BaseModel):
    ok: bool
    id: Optional[int] = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
