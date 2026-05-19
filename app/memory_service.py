import json
import logging
import re
from typing import Any, Optional

from fastapi import HTTPException, status

from app.db import Database
from app.embeddings import EmbeddingProvider
from app.faiss_store import FaissStore
from app.schemas import MemoryAddRequest, MemoryDeleteRequest, MemorySearchRequest, MemoryUpdateRequest


logger = logging.getLogger("brainclaw.memory")

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\b[A-Za-z0-9_]*(?:api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token)[A-Za-z0-9_]*\s*[:=]\s*[^\s]{8,}", re.IGNORECASE),
    re.compile(r"\bpassword\s*[:=]\s*[^\s]{6,}", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bssh-rsa\s+[A-Za-z0-9+/=]{80,}", re.IGNORECASE),
]

LOG_REDACTIONS = [
    (re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
    (re.compile(r"-----BEGIN .*?PRIVATE KEY-----.*?-----END .*?PRIVATE KEY-----", re.IGNORECASE | re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
]


def reject_obvious_secrets(content: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(content):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="content appears to contain a secret and was rejected",
            )


def redact_for_log(value: str, max_chars: int = 160) -> str:
    redacted = value
    for pattern, replacement in LOG_REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    if len(redacted) > max_chars:
        return f"{redacted[:max_chars]}...[truncated]"
    return redacted


def row_to_memory(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["tags"] = json.loads(data.pop("tags_json") or "[]")
    return data


def chunk_content(content: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = content.strip()
    if len(normalized) <= chunk_size:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = max(normalized.rfind("\n", start, end), normalized.rfind(". ", start, end), normalized.rfind(" ", start, end))
            if boundary > start + int(chunk_size * 0.5):
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


class MemoryService:
    def __init__(self, db: Database, embeddings: EmbeddingProvider, faiss_store: FaissStore, chunk_size: int, chunk_overlap: int):
        self.db = db
        self.embeddings = embeddings
        self.faiss_store = faiss_store
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def add_memory(self, request: MemoryAddRequest) -> dict[str, Any]:
        reject_obvious_secrets(request.content)
        chunks = chunk_content(request.content, self.chunk_size, self.chunk_overlap)
        payload = request.model_dump()
        memory_id = self.db.create_memory(payload, chunks)
        chunk_rows = self.db.get_chunks_for_memory(memory_id)
        vectors = self.embeddings.embed_texts([row["text"] for row in chunk_rows])
        mappings = [{"type": "memory", "chunk_id": int(row["id"]), "memory_id": memory_id} for row in chunk_rows]
        self.faiss_store.add(vectors, mappings)
        logger.info(
            "memory_added",
            extra={
                "memory_id": memory_id,
                "agent_id": request.agent_id,
                "workspace": request.workspace,
                "source": request.source,
                "memory_type": request.memory_type,
                "tags": request.tags,
                "importance": request.importance,
                "chunks": len(chunks),
                "content_preview": redact_for_log(request.content[:80]),
            },
        )
        return {"ok": True, "id": memory_id, "message": "memory added", "details": {"chunks": len(chunks)}}

    def get_memory(self, memory_id: int) -> dict[str, Any]:
        row = self.db.get_memory(memory_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        return row_to_memory(row)

    def search_memory(self, request: MemorySearchRequest) -> list[dict[str, Any]]:
        vector = self.embeddings.embed_query(request.query)
        probe_limit = min(max(request.top_k * 10, request.top_k), max(self.faiss_store.vector_count, request.top_k))
        raw_results = self.faiss_store.search(vector, probe_limit)
        results: list[dict[str, Any]] = []
        seen_memories: set[int] = set()
        required_tags = set(request.tags or [])

        for raw in raw_results:
            if raw.get("type") != "memory" or raw["score"] < request.min_score:
                continue
            row = self.db.get_chunk_with_memory(raw["chunk_id"])
            if row is None:
                continue
            item = row_to_memory(row)
            if item["agent_id"] != request.agent_id or item["workspace"] != request.workspace:
                continue
            if request.memory_type and item["memory_type"] != request.memory_type:
                continue
            if required_tags and not required_tags.issubset(set(item["tags"])):
                continue
            if item["id"] in seen_memories:
                continue
            seen_memories.add(item["id"])
            item["score"] = raw["score"]
            results.append(item)
            if len(results) >= request.top_k:
                break

        logger.info(
            "memory_search",
            extra={
                "agent_id": request.agent_id,
                "workspace": request.workspace,
                "top_k": request.top_k,
                "min_score": request.min_score,
                "tags": request.tags or [],
                "memory_type": request.memory_type,
                "matches": len(results),
                "query_preview": redact_for_log(request.query),
            },
        )
        return results

    def delete_memory(self, request: MemoryDeleteRequest) -> dict[str, Any]:
        deleted = self.db.delete_memory(request.id, request.agent_id, request.workspace)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        rebuilt = self.rebuild_index()
        logger.info("memory_deleted", extra={"memory_id": request.id, "agent_id": request.agent_id, "workspace": request.workspace})
        return {"ok": True, "id": request.id, "message": "memory deleted", "details": rebuilt["details"]}

    def update_memory(self, request: MemoryUpdateRequest) -> dict[str, Any]:
        existing = self.db.get_memory(request.id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        existing_data = row_to_memory(existing)
        if existing_data["agent_id"] != request.agent_id or existing_data["workspace"] != request.workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")

        updates = request.model_dump(exclude_unset=True, exclude={"id", "agent_id", "workspace"})
        chunks: Optional[list[str]] = None
        if "content" in updates:
            reject_obvious_secrets(updates["content"])
            chunks = chunk_content(updates["content"], self.chunk_size, self.chunk_overlap)
        updated = self.db.update_memory(request.id, updates, chunks)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        rebuilt = self.rebuild_index()
        logger.info(
            "memory_updated",
            extra={
                "memory_id": request.id,
                "agent_id": request.agent_id,
                "workspace": request.workspace,
                "fields": sorted(updates.keys()),
            },
        )
        return {"ok": True, "id": request.id, "message": "memory updated", "details": rebuilt["details"]}

    def rebuild_index(self) -> dict[str, Any]:
        rows = self.db.iter_active_chunks()
        file_rows = self.db.iter_active_file_chunks()
        texts = [row["chunk_text"] for row in rows] + [row["chunk_text"] for row in file_rows]
        vectors = self.embeddings.embed_texts(texts)
        mappings: list[dict[str, Any]] = [
            {"type": "memory", "chunk_id": int(row["chunk_id"]), "memory_id": int(row["id"])}
            for row in rows
        ]
        mappings.extend(
            {"type": "file", "chunk_id": int(row["file_chunk_id"]), "file_id": int(row["id"])}
            for row in file_rows
        )
        self.faiss_store.rebuild(vectors, mappings)
        return {"ok": True, "id": None, "message": "index rebuilt", "details": {"vectors": len(mappings)}}
