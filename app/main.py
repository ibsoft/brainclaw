import logging
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Path, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.wsgi import WSGIMiddleware

from app.admin import create_admin_app
from app.config import Settings, get_settings
from app.db import Database
from app.embeddings import EmbeddingProvider
from app.faiss_store import FaissStore
from app.file_service import FileService
from app.memory_service import MemoryService, redact_for_log
from app.security import Principal, require_scope, verify_api_key
from app.schemas import (
    FileSearchRequest,
    FileSearchResponse,
    FileUploadResponse,
    HealthResponse,
    MemoryAddRequest,
    MemoryDeleteRequest,
    MemoryGetResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryUpdateRequest,
    StatusResponse,
)


class JsonFormatter(logging.Formatter):
    reserved = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self.reserved and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    formatter = JsonFormatter()
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        settings.log_file,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stream_handler)
    root.addHandler(file_handler)
    root.setLevel(settings.log_level.upper())


settings = get_settings()
configure_logging(settings)
logger = logging.getLogger("brainclaw.api")

db = Database(settings.sqlite_path)
embedding_provider = EmbeddingProvider(settings)
faiss_store = FaissStore(settings)
memory_service = MemoryService(
    db=db,
    embeddings=embedding_provider,
    faiss_store=faiss_store,
    chunk_size=settings.chunk_size_chars,
    chunk_overlap=settings.chunk_overlap_chars,
)
file_service = FileService(settings=settings, db=db, embeddings=embedding_provider, faiss_store=faiss_store)

app = FastAPI(title=settings.app_name, version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client": request.client.host if request.client else None,
            },
        )


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)


def require_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> Principal:
    if not settings.memory_api_key:
        if settings.allow_missing_api_key:
            return Principal(role="admin")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MEMORY_API_KEY is not configured",
        )
    return verify_api_key(settings, db, x_api_key)


Auth = Depends(require_api_key)


@app.get("/health", response_model=HealthResponse)
def health(_: Annotated[Principal, Auth]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        ok=True,
        app=settings.app_name,
        index_vectors=faiss_store.vector_count,
        sqlite_path=str(settings.sqlite_path),
        faiss_index_path=str(settings.faiss_index_path),
        embedding_model_name=settings.embedding_model_name,
    )


@app.post("/memory/add", response_model=StatusResponse)
def add_memory(request: MemoryAddRequest, principal: Annotated[Principal, Auth]) -> StatusResponse:
    require_scope(principal, request.agent_id, request.workspace)
    return StatusResponse(**memory_service.add_memory(request))


@app.post("/memory/search", response_model=MemorySearchResponse)
def search_memory(request: MemorySearchRequest, principal: Annotated[Principal, Auth]) -> dict:
    require_scope(principal, request.agent_id, request.workspace)
    results = memory_service.search_memory(request)
    return {"status": "success", "ok": True, "count": len(results), "results": results}


@app.post("/memory/delete", response_model=StatusResponse)
def delete_memory(request: MemoryDeleteRequest, principal: Annotated[Principal, Auth]) -> StatusResponse:
    require_scope(principal, request.agent_id, request.workspace)
    return StatusResponse(**memory_service.delete_memory(request))


@app.post("/memory/update", response_model=StatusResponse)
def update_memory(request: MemoryUpdateRequest, principal: Annotated[Principal, Auth]) -> StatusResponse:
    require_scope(principal, request.agent_id, request.workspace)
    return StatusResponse(**memory_service.update_memory(request))


@app.get("/memory/{id}", response_model=MemoryGetResponse)
def get_memory(
    id: Annotated[int, Path(gt=0)],
    agent_id: Annotated[str, Query(min_length=1, max_length=128)],
    workspace: Annotated[str, Query(min_length=1, max_length=256)],
    principal: Annotated[Principal, Auth],
) -> dict:
    require_scope(principal, agent_id, workspace)
    return {"status": "success", "ok": True, "memory": memory_service.get_memory(id, agent_id, workspace)}


@app.post("/memory/rebuild-index", response_model=StatusResponse)
def rebuild_index(principal: Annotated[Principal, Auth]) -> StatusResponse:
    if principal.is_admin:
        return StatusResponse(**memory_service.rebuild_index())
    return StatusResponse(**memory_service.rebuild_index(principal.agent_id, principal.workspace))


@app.post("/files/upload", response_model=FileUploadResponse)
async def upload_file(
    agent_id: Annotated[str, Form(min_length=1, max_length=128)],
    workspace: Annotated[str, Form(min_length=1, max_length=256)],
    source: Annotated[str, Form(min_length=1, max_length=256)],
    principal: Annotated[Principal, Auth],
    tags: Annotated[str, Form()] = "",
    file: UploadFile = File(...),
) -> FileUploadResponse:
    require_scope(principal, agent_id, workspace)
    return FileUploadResponse(**await file_service.upload_file(agent_id, workspace, source, tags, file))


@app.post("/files/search", response_model=FileSearchResponse)
def search_files(request: FileSearchRequest, principal: Annotated[Principal, Auth]) -> dict:
    require_scope(principal, request.agent_id, request.workspace)
    results = file_service.search_files(request)
    return {"status": "success", "ok": True, "count": len(results), "results": results}


@app.delete("/files/{file_id}", response_model=StatusResponse)
def delete_file(
    file_id: Annotated[int, Path(gt=0)],
    agent_id: Annotated[str, Query(min_length=1, max_length=128)],
    workspace: Annotated[str, Query(min_length=1, max_length=256)],
    principal: Annotated[Principal, Auth],
) -> StatusResponse:
    require_scope(principal, agent_id, workspace)
    return StatusResponse(**file_service.delete_file(file_id, agent_id, workspace))


@app.post("/files/reindex", response_model=StatusResponse)
def reindex_files(principal: Annotated[Principal, Auth]) -> StatusResponse:
    if principal.is_admin:
        return StatusResponse(**file_service.reindex_files_and_memories())
    return StatusResponse(**file_service.reindex_files_and_memories(principal.agent_id, principal.workspace))


app.mount("/admin", WSGIMiddleware(create_admin_app(settings, db, memory_service, file_service, faiss_store)))


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "failure",
            "ok": False,
            "message": exc.detail if isinstance(exc.detail, str) else "request failed",
            "details": exc.detail if not isinstance(exc.detail, str) else {},
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "failure",
            "ok": False,
            "message": "validation failed",
            "details": {"errors": exc.errors()},
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("unhandled_exception", extra={"error": redact_for_log(str(exc))})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "failure", "ok": False, "message": "internal server error", "details": {}},
    )
