import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, sqlite_path: Path):
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.sqlite_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    source TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 0.5,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    source TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    content_type TEXT,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS file_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_memories_scope
                    ON memories(agent_id, workspace, deleted);
                CREATE INDEX IF NOT EXISTS idx_memories_type
                    ON memories(memory_type, deleted);
                CREATE INDEX IF NOT EXISTS idx_chunks_memory
                    ON chunks(memory_id, deleted);
                CREATE INDEX IF NOT EXISTS idx_files_scope
                    ON files(agent_id, workspace, deleted);
                CREATE INDEX IF NOT EXISTS idx_files_sha
                    ON files(sha256, deleted);
                CREATE INDEX IF NOT EXISTS idx_file_chunks_file
                    ON file_chunks(file_id, deleted);
                """
            )

    def create_memory(self, payload: dict[str, Any], chunks: list[str]) -> int:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO memories
                    (agent_id, workspace, source, memory_type, content, tags_json, importance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["agent_id"],
                    payload["workspace"],
                    payload["source"],
                    payload["memory_type"],
                    payload["content"],
                    json.dumps(payload["tags"]),
                    payload["importance"],
                    now,
                    now,
                ),
            )
            memory_id = int(cursor.lastrowid)
            conn.executemany(
                """
                INSERT INTO chunks (memory_id, chunk_index, text, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(memory_id, index, text, now, now) for index, text in enumerate(chunks)],
            )
            return memory_id

    def get_memory(self, memory_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT m.*,
                       COUNT(c.id) AS chunk_count
                FROM memories m
                LEFT JOIN chunks c ON c.memory_id = m.id AND c.deleted = 0
                WHERE m.id = ? AND m.deleted = 0
                GROUP BY m.id
                """,
                (memory_id,),
            ).fetchone()

    def update_memory(self, memory_id: int, updates: dict[str, Any], chunks: Optional[list[str]]) -> bool:
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM memories WHERE id = ? AND deleted = 0",
                (memory_id,),
            ).fetchone()
            if not existing:
                return False

            fields: list[str] = []
            values: list[Any] = []
            for key in ("source", "memory_type", "content", "importance"):
                if key in updates:
                    fields.append(f"{key} = ?")
                    values.append(updates[key])
            if "tags" in updates:
                fields.append("tags_json = ?")
                values.append(json.dumps(updates["tags"]))
            fields.append("updated_at = ?")
            values.append(now)
            values.append(memory_id)
            conn.execute(f"UPDATE memories SET {', '.join(fields)} WHERE id = ?", values)

            if chunks is not None:
                conn.execute("UPDATE chunks SET deleted = 1, updated_at = ? WHERE memory_id = ?", (now, memory_id))
                conn.executemany(
                    """
                    INSERT INTO chunks (memory_id, chunk_index, text, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [(memory_id, index, text, now, now) for index, text in enumerate(chunks)],
                )
            return True

    def delete_memory(self, memory_id: int, agent_id: str, workspace: str) -> bool:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE memories
                SET deleted = 1, updated_at = ?
                WHERE id = ? AND agent_id = ? AND workspace = ? AND deleted = 0
                """,
                (now, memory_id, agent_id, workspace),
            )
            if cursor.rowcount == 0:
                return False
            conn.execute("UPDATE chunks SET deleted = 1, updated_at = ? WHERE memory_id = ?", (now, memory_id))
            return True

    def get_chunks_for_memory(self, memory_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT c.*
                FROM chunks c
                JOIN memories m ON m.id = c.memory_id
                WHERE c.memory_id = ? AND c.deleted = 0 AND m.deleted = 0
                ORDER BY c.chunk_index ASC
                """,
                (memory_id,),
            ).fetchall()

    def iter_active_chunks(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT c.id AS chunk_id, c.text AS chunk_text, c.chunk_index, m.*
                FROM chunks c
                JOIN memories m ON m.id = c.memory_id
                WHERE c.deleted = 0 AND m.deleted = 0
                ORDER BY c.id ASC
                """
            ).fetchall()

    def get_chunk_with_memory(self, chunk_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT c.id AS chunk_id, c.text AS chunk_text, c.chunk_index, m.*
                FROM chunks c
                JOIN memories m ON m.id = c.memory_id
                WHERE c.id = ? AND c.deleted = 0 AND m.deleted = 0
                """,
                (chunk_id,),
            ).fetchone()

    def find_active_file_by_sha(self, sha256: str, agent_id: str, workspace: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT *
                FROM files
                WHERE sha256 = ? AND agent_id = ? AND workspace = ? AND deleted = 0
                LIMIT 1
                """,
                (sha256, agent_id, workspace),
            ).fetchone()

    def create_file(self, payload: dict[str, Any], chunks: list[str]) -> int:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO files
                    (agent_id, workspace, source, original_filename, stored_filename, extension,
                     content_type, sha256, size_bytes, tags_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["agent_id"],
                    payload["workspace"],
                    payload["source"],
                    payload["original_filename"],
                    payload["stored_filename"],
                    payload["extension"],
                    payload.get("content_type"),
                    payload["sha256"],
                    payload["size_bytes"],
                    json.dumps(payload["tags"]),
                    now,
                    now,
                ),
            )
            file_id = int(cursor.lastrowid)
            conn.executemany(
                """
                INSERT INTO file_chunks (file_id, chunk_index, text, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(file_id, index, text, now, now) for index, text in enumerate(chunks)],
            )
            return file_id

    def get_file(self, file_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT f.*,
                       COUNT(fc.id) AS chunk_count
                FROM files f
                LEFT JOIN file_chunks fc ON fc.file_id = f.id AND fc.deleted = 0
                WHERE f.id = ? AND f.deleted = 0
                GROUP BY f.id
                """,
                (file_id,),
            ).fetchone()

    def get_chunks_for_file(self, file_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT fc.*
                FROM file_chunks fc
                JOIN files f ON f.id = fc.file_id
                WHERE fc.file_id = ? AND fc.deleted = 0 AND f.deleted = 0
                ORDER BY fc.chunk_index ASC
                """,
                (file_id,),
            ).fetchall()

    def get_file_chunk_with_file(self, chunk_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT fc.id AS file_chunk_id, fc.text AS chunk_text, fc.chunk_index, f.*
                FROM file_chunks fc
                JOIN files f ON f.id = fc.file_id
                WHERE fc.id = ? AND fc.deleted = 0 AND f.deleted = 0
                """,
                (chunk_id,),
            ).fetchone()

    def iter_active_file_chunks(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT fc.id AS file_chunk_id, fc.text AS chunk_text, fc.chunk_index, f.*
                FROM file_chunks fc
                JOIN files f ON f.id = fc.file_id
                WHERE fc.deleted = 0 AND f.deleted = 0
                ORDER BY fc.id ASC
                """
            ).fetchall()

    def delete_file(self, file_id: int, agent_id: str, workspace: str) -> bool:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE files
                SET deleted = 1, updated_at = ?
                WHERE id = ? AND agent_id = ? AND workspace = ? AND deleted = 0
                """,
                (now, file_id, agent_id, workspace),
            )
            if cursor.rowcount == 0:
                return False
            conn.execute("UPDATE file_chunks SET deleted = 1, updated_at = ? WHERE file_id = ?", (now, file_id))
            return True
