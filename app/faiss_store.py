import json
import logging
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
        self.index = self._load_or_create_index()
        self.id_map = self._load_id_map()

    def _load_or_create_index(self) -> faiss.IndexFlatIP:
        if self.index_path.exists() and self.index_path.stat().st_size > 0:
            index = faiss.read_index(str(self.index_path))
            logger.info("faiss_index_loaded", extra={"vectors": index.ntotal, "path": str(self.index_path)})
            return index
        logger.info("faiss_index_created", extra={"dimension": self.settings.embedding_dimension})
        return faiss.IndexFlatIP(self.settings.embedding_dimension)

    def _load_id_map(self) -> list[dict[str, Any]]:
        if not self.id_map_path.exists():
            return []
        with self.id_map_path.open("r", encoding="utf-8") as handle:
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

    def persist(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.id_map_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.index_path))
        tmp_path = self.id_map_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self.id_map, handle, indent=2)
        tmp_path.replace(self.id_map_path)

    def add(self, vectors: np.ndarray, mappings: list[dict[str, Any]]) -> None:
        if vectors.shape[0] != len(mappings):
            raise ValueError("vector and mapping counts differ")
        if vectors.shape[0] == 0:
            return
        with self.lock:
            self.index.add(vectors)
            self.id_map.extend(mappings)
            self.persist()
            logger.info("faiss_vectors_added", extra={"added": len(mappings), "total": self.index.ntotal})

    def search(self, vector: np.ndarray, limit: int) -> list[dict[str, Any]]:
        with self.lock:
            if self.index.ntotal == 0:
                return []
            safe_limit = max(1, min(limit, self.index.ntotal))
            scores, positions = self.index.search(vector, safe_limit)
            results: list[dict[str, Any]] = []
            for score, position in zip(scores[0], positions[0]):
                if position < 0 or position >= len(self.id_map):
                    continue
                mapped = self.id_map[int(position)]
                result = {"score": float(score), "position": int(position), **mapped}
                results.append(result)
            return results

    def rebuild(self, vectors: np.ndarray, mappings: list[dict[str, Any]]) -> None:
        with self.lock:
            index = faiss.IndexFlatIP(self.settings.embedding_dimension)
            if vectors.shape[0] > 0:
                index.add(vectors)
            self.index = index
            self.id_map = mappings
            self.persist()
            logger.info("faiss_index_rebuilt", extra={"vectors": self.index.ntotal})

    @property
    def vector_count(self) -> int:
        return int(self.index.ntotal)
