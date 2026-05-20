import json
import logging
import hashlib
import threading
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.config import Settings


logger = logging.getLogger("brainclaw.faiss")


class FaissStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.index_path = Path(settings.faiss_index_path)
        self.id_map_path = Path(settings.id_map_path)
        self.lock = threading.RLock()
        self._stores: dict[str, tuple[faiss.IndexFlatIP, list[dict[str, Any]]]] = {}
        self.index = self._load_or_create_index(self.index_path)
        self.id_map = self._load_id_map(self.id_map_path)

    def _scope_key(self, agent_id: str | None, workspace: str | None) -> str:
        if not self.settings.isolate_indexes or not agent_id or not workspace:
            return "__global__"
        digest = hashlib.sha256(f"{agent_id}\0{workspace}".encode("utf-8")).hexdigest()
        return digest

    def _paths_for_scope(self, agent_id: str | None, workspace: str | None) -> tuple[Path, Path]:
        scope_key = self._scope_key(agent_id, workspace)
        if scope_key == "__global__":
            return self.index_path, self.id_map_path
        return self.settings.index_dir / f"{scope_key}.faiss", self.settings.index_dir / f"{scope_key}.id_map.json"

    def _store_for_scope(self, agent_id: str | None = None, workspace: str | None = None) -> tuple[faiss.IndexFlatIP, list[dict[str, Any]]]:
        scope_key = self._scope_key(agent_id, workspace)
        if scope_key == "__global__":
            return self.index, self.id_map
        if scope_key not in self._stores:
            index_path, id_map_path = self._paths_for_scope(agent_id, workspace)
            self._stores[scope_key] = (self._load_or_create_index(index_path), self._load_id_map(id_map_path))
        return self._stores[scope_key]

    def _load_or_create_index(self, path: Path) -> faiss.IndexFlatIP:
        if path.exists() and path.stat().st_size > 0:
            index = faiss.read_index(str(path))
            logger.info("faiss_index_loaded", extra={"vectors": index.ntotal, "path": str(path)})
            return index
        logger.info("faiss_index_created", extra={"dimension": self.settings.embedding_dimension})
        return faiss.IndexFlatIP(self.settings.embedding_dimension)

    def _load_id_map(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            raise ValueError("id_map.json must contain a list")
        normalized = []
        for item in data:
            item_type = str(item.get("type") or "memory")
            normalized_item = {"type": item_type, "chunk_id": int(item["chunk_id"])}
            if item_type == "file":
                normalized_item["file_id"] = int(item["file_id"])
            else:
                normalized_item["memory_id"] = int(item["memory_id"])
            normalized.append(normalized_item)
        return normalized

    def persist(self, agent_id: str | None = None, workspace: str | None = None) -> None:
        index, id_map = self._store_for_scope(agent_id, workspace)
        index_path, id_map_path = self._paths_for_scope(agent_id, workspace)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        id_map_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(index_path))
        tmp_path = id_map_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(id_map, handle, indent=2)
        tmp_path.replace(id_map_path)

    def add(self, vectors: np.ndarray, mappings: list[dict[str, Any]], agent_id: str | None = None, workspace: str | None = None) -> None:
        if vectors.shape[0] != len(mappings):
            raise ValueError("vector and mapping counts differ")
        if vectors.shape[0] == 0:
            return
        with self.lock:
            index, id_map = self._store_for_scope(agent_id, workspace)
            index.add(vectors)
            id_map.extend(mappings)
            self.persist(agent_id, workspace)
            logger.info("faiss_vectors_added", extra={"added": len(mappings), "total": index.ntotal, "agent_id": agent_id, "workspace": workspace})

    def search(self, vector: np.ndarray, limit: int, agent_id: str | None = None, workspace: str | None = None) -> list[dict[str, Any]]:
        with self.lock:
            index, id_map = self._store_for_scope(agent_id, workspace)
            if index.ntotal == 0:
                return []
            safe_limit = max(1, min(limit, index.ntotal))
            scores, positions = index.search(vector, safe_limit)
            results: list[dict[str, Any]] = []
            for score, position in zip(scores[0], positions[0]):
                if position < 0 or position >= len(id_map):
                    continue
                mapped = id_map[int(position)]
                result = {"score": float(score), "position": int(position), **mapped}
                results.append(result)
            return results

    def rebuild(self, vectors: np.ndarray, mappings: list[dict[str, Any]], agent_id: str | None = None, workspace: str | None = None) -> None:
        with self.lock:
            index = faiss.IndexFlatIP(self.settings.embedding_dimension)
            if vectors.shape[0] > 0:
                index.add(vectors)
            scope_key = self._scope_key(agent_id, workspace)
            if scope_key == "__global__":
                self.index = index
                self.id_map = mappings
            else:
                self._stores[scope_key] = (index, mappings)
            self.persist(agent_id, workspace)
            logger.info("faiss_index_rebuilt", extra={"vectors": index.ntotal, "agent_id": agent_id, "workspace": workspace})

    def vector_count_for_scope(self, agent_id: str, workspace: str) -> int:
        index, _ = self._store_for_scope(agent_id, workspace)
        return int(index.ntotal)

    @property
    def vector_count(self) -> int:
        if not self.settings.isolate_indexes:
            return int(self.index.ntotal)
        total = sum(index.ntotal for index, _ in self._stores.values())
        for index_file in self.settings.index_dir.glob("*.faiss"):
            scope_key = index_file.name.removesuffix(".faiss")
            if scope_key in self._stores:
                continue
            try:
                total += int(faiss.read_index(str(index_file)).ntotal)
            except Exception:
                logger.warning("faiss_index_count_failed", extra={"path": str(index_file)})
        return int(total)
