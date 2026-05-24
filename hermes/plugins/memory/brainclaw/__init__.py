"""Hermes memory plugin for BrainClaw HTTP memory."""

from __future__ import annotations

import json
import logging
import os
import shlex
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

try:
    from agent.memory_provider import MemoryProvider
except ImportError:
    class MemoryProvider:  # type: ignore[no-redef]
        pass


HERMES_ENV_CONF = Path("/etc/hermes/environment.conf")
OPENCLAW_ENV_CONF = Path("/etc/openclaw/environment.conf")
ENV_CONF_PATHS = (HERMES_ENV_CONF, OPENCLAW_ENV_CONF)
DEFAULT_URL = "http://127.0.0.1:8757"
logger = logging.getLogger(__name__)


BRAINCLAW_SEARCH_SCHEMA = {
    "name": "brainclaw_search",
    "description": "Search BrainClaw memory for the active Hermes scope.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Focused search query."},
            "top_k": {"type": "integer", "description": "Maximum results to return. Default 3."},
            "min_score": {"type": "number", "description": "Minimum vector score. Default 0.25."},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tag filter.",
            },
            "memory_type": {"type": "string", "description": "Optional memory_type filter."},
        },
        "required": ["query"],
    },
}

BRAINCLAW_ADD_SCHEMA = {
    "name": "brainclaw_add",
    "description": "Add a compact memory to BrainClaw for the active Hermes scope. Never store secrets.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Compact memory content."},
            "source": {"type": "string", "description": "Memory source. Default hermes-session."},
            "memory_type": {"type": "string", "description": "Memory type. Default note."},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags. Include exactly one horizon tag: session, short, or long.",
            },
            "importance": {"type": "number", "description": "Importance from 0.0 to 1.0. Default 0.5."},
        },
        "required": ["content"],
    },
}

BRAINCLAW_FILES_SEARCH_SCHEMA = {
    "name": "brainclaw_files_search",
    "description": "Search uploaded document memory in BrainClaw for the active Hermes scope.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Focused search query."},
            "top_k": {"type": "integer", "description": "Maximum results to return. Default 3."},
            "min_score": {"type": "number", "description": "Minimum vector score. Default 0.25."},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tag filter.",
            },
        },
        "required": ["query"],
    },
}

TOOL_SCHEMAS = [
    BRAINCLAW_SEARCH_SCHEMA,
    BRAINCLAW_ADD_SCHEMA,
    BRAINCLAW_FILES_SEARCH_SCHEMA,
]


class BrainClawMemoryError(RuntimeError):
    """Raised when BrainClaw memory is not available."""


@dataclass(frozen=True)
class BrainClawConfig:
    url: str
    api_key: str
    agent_id: str
    workspace: str


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    if not os.access(path, os.R_OK):
        raise BrainClawMemoryError(f"BrainClaw environment config exists but is not readable: {path}")

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parts = shlex.split(raw_value, comments=False, posix=True)
            value = parts[0] if parts else ""
        except ValueError:
            value = raw_value.strip().strip("'\"")
        values[key] = value
    return values


def _load_env_values() -> dict[str, str]:
    for path in ENV_CONF_PATHS:
        values = _load_env_file(path)
        if values:
            return values
    return {}


def _setting(values: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = values.get(name) or os.environ.get(name)
        if value:
            return value
    return default


def load_config() -> BrainClawConfig:
    values = _load_env_values()
    api_key = _setting(values, "BRAINCLAW_API_KEY", "MEMORY_API_KEY")
    if not api_key:
        raise BrainClawMemoryError("missing BRAINCLAW_API_KEY or MEMORY_API_KEY")

    return BrainClawConfig(
        url=_setting(values, "BRAINCLAW_URL", default=DEFAULT_URL).rstrip("/"),
        api_key=api_key,
        agent_id=_setting(values, "HERMES_AGENT_ID", "OPENCLAW_AGENT_ID", "AGENT_ID", default="hermes"),
        workspace=_setting(values, "HERMES_WORKSPACE", "OPENCLAW_WORKSPACE", "WORKSPACE", default="default"),
    )


class BrainClawMemory:
    """HTTP-only BrainClaw memory adapter for Hermes."""

    def __init__(self, config: BrainClawConfig | None = None) -> None:
        self.config = config or load_config()

    def health(self) -> Any:
        return self._request("GET", "/health")

    def search(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.25,
        tags: list[str] | None = None,
        memory_type: str | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "query": query,
            "top_k": top_k,
            "min_score": min_score,
        }
        if tags:
            payload["tags"] = tags
        if memory_type:
            payload["memory_type"] = memory_type
        return self._request("POST", "/memory/search", self._scoped(payload))

    def add(
        self,
        content: str,
        source: str = "hermes-session",
        memory_type: str = "note",
        tags: list[str] | None = None,
        importance: float = 0.5,
    ) -> Any:
        return self._request(
            "POST",
            "/memory/add",
            self._scoped(
                {
                    "source": source,
                    "memory_type": memory_type,
                    "content": content,
                    "tags": tags or ["short", "hermes"],
                    "importance": importance,
                }
            ),
        )

    def update(
        self,
        memory_id: int,
        source: str | None = None,
        memory_type: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
        importance: float | None = None,
    ) -> Any:
        payload: dict[str, Any] = {"id": memory_id}
        if source is not None:
            payload["source"] = source
        if memory_type is not None:
            payload["memory_type"] = memory_type
        if content is not None:
            payload["content"] = content
        if tags is not None:
            payload["tags"] = tags
        if importance is not None:
            payload["importance"] = importance
        return self._request("POST", "/memory/update", self._scoped(payload))

    def delete(self, memory_id: int) -> Any:
        return self._request("POST", "/memory/delete", self._scoped({"id": memory_id}))

    def files_search(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.25,
        tags: list[str] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "query": query,
            "top_k": top_k,
            "min_score": min_score,
        }
        if tags:
            payload["tags"] = tags
        return self._request("POST", "/files/search", self._scoped(payload))

    def _scoped(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent_id": self.config.agent_id,
            "workspace": self.config.workspace,
            **payload,
        }

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = None
        headers = {"X-API-Key": self.config.api_key}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(f"{self.config.url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise BrainClawMemoryError(f"HTTP {exc.code} {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BrainClawMemoryError(f"{path}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise BrainClawMemoryError(f"{path}: request timed out") from exc

        return json.loads(body) if body else None


class BrainClawMemoryProvider(MemoryProvider):
    """Hermes MemoryProvider implementation backed by BrainClaw HTTP."""

    def __init__(self) -> None:
        self._memory: BrainClawMemory | None = None
        self._session_id = ""

    @property
    def name(self) -> str:
        return "brainclaw"

    def is_available(self) -> bool:
        """Check configuration only. Hermes requires no network calls here."""
        try:
            load_config()
        except BrainClawMemoryError:
            return False
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        agent_context = kwargs.get("agent_context", "")
        platform = kwargs.get("platform", "cli")
        if agent_context in {"cron", "flush"} or platform == "cron":
            logger.debug("BrainClaw memory skipped for context=%s platform=%s", agent_context, platform)
            return
        self._session_id = session_id
        self._memory = BrainClawMemory()

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "api_key",
                "description": "BrainClaw API key",
                "secret": True,
                "required": True,
                "env_var": "BRAINCLAW_API_KEY",
            },
            {
                "key": "url",
                "description": "BrainClaw base URL",
                "default": DEFAULT_URL,
                "env_var": "BRAINCLAW_URL",
            },
            {
                "key": "agent_id",
                "description": "BrainClaw agent_id scope for Hermes",
                "default": "hermes",
                "env_var": "HERMES_AGENT_ID",
            },
            {
                "key": "workspace",
                "description": "BrainClaw workspace scope for Hermes",
                "default": "default",
                "env_var": "HERMES_WORKSPACE",
            },
        ]

    def system_prompt_block(self) -> str:
        if not self._memory:
            return ""
        return (
            "# BrainClaw Memory\n"
            "Active for Hermes. Use brainclaw_search for memory recall, "
            "brainclaw_files_search for uploaded document recall, and brainclaw_add "
            "only for compact non-secret facts that should persist."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return TOOL_SCHEMAS if self._memory else []

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        memory = self._memory or BrainClawMemory()
        try:
            if tool_name == "brainclaw_search":
                result = memory.search(
                    query=str(args["query"]),
                    top_k=int(args.get("top_k", 3)),
                    min_score=float(args.get("min_score", 0.25)),
                    tags=args.get("tags"),
                    memory_type=args.get("memory_type"),
                )
            elif tool_name == "brainclaw_add":
                result = memory.add(
                    content=str(args["content"]),
                    source=str(args.get("source") or "hermes-session"),
                    memory_type=str(args.get("memory_type") or "note"),
                    tags=args.get("tags") or ["short", "hermes"],
                    importance=float(args.get("importance", 0.5)),
                )
            elif tool_name == "brainclaw_files_search":
                result = memory.files_search(
                    query=str(args["query"]),
                    top_k=int(args.get("top_k", 3)),
                    min_score=float(args.get("min_score", 0.25)),
                    tags=args.get("tags"),
                )
            else:
                result = {"ok": False, "error": f"unknown BrainClaw tool: {tool_name}"}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        return json.dumps(result, ensure_ascii=False, default=str)


def register(ctx) -> None:
    """Hermes plugin discovery entry point."""
    ctx.register_memory_provider(BrainClawMemoryProvider())


__all__ = [
    "BrainClawConfig",
    "BrainClawMemory",
    "BrainClawMemoryProvider",
    "BrainClawMemoryError",
    "load_config",
    "register",
]
