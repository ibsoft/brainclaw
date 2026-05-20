import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from app.config import Settings
from app.db import Database


@dataclass(frozen=True)
class Principal:
    role: str
    agent_id: str | None = None
    workspace: str | None = None
    api_key_id: int | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"bc_{secrets.token_urlsafe(32)}"


def key_prefix(api_key: str) -> str:
    return api_key[:10]


def verify_api_key(settings: Settings, db: Database, api_key: str | None) -> Principal:
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing API key")

    if settings.memory_api_key and hmac.compare_digest(api_key, settings.memory_api_key):
        return Principal(role="admin")

    row = db.get_api_key_by_hash(hash_api_key(api_key))
    if row is not None:
        db.touch_api_key(int(row["id"]))
        return Principal(
            role=str(row["role"]),
            agent_id=row["agent_id"],
            workspace=row["workspace"],
            api_key_id=int(row["id"]),
        )

    if not settings.memory_api_key and settings.allow_missing_api_key:
        return Principal(role="admin")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")


def require_scope(principal: Principal, agent_id: str, workspace: str) -> None:
    if principal.is_admin:
        return
    if principal.agent_id != agent_id or principal.workspace != workspace:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key is not allowed for this agent/workspace")


def row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)
