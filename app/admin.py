import io
import json
import math
import re
import secrets
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, flash, redirect, render_template_string, request, send_file, session, url_for
from markupsafe import Markup, escape
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import Database
from app.faiss_store import FaissStore
from app.file_service import FileService, parse_tags
from app.memory_service import MemoryService, row_to_memory
from app.schemas import MemoryAddRequest, MemoryDeleteRequest, MemoryUpdateRequest
from app.security import generate_api_key, hash_api_key, key_prefix


BASE_TEMPLATE = """
<!doctype html>
<html lang="en" data-bs-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }} · BrainClaw</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" rel="stylesheet">
  <style>
    body { background: #111827; }
    .navbar, .panel { background: #172033; border: 1px solid #273449; }
    .panel { border-radius: .5rem; }
    .table { --bs-table-bg: transparent; }
    .content-cell { max-width: 520px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .secret-box { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .sql-editor { min-height: 180px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .auth-shell { min-height: calc(100vh - 7rem); display: grid; place-items: center; }
    .auth-card { width: min(100%, 30rem); }
    .clickable-row { cursor: pointer; }
    .memory-full-content { white-space: pre-wrap; max-height: 55vh; overflow: auto; }
    .loading-overlay {
      position: fixed; inset: 0; display: none; place-items: center; z-index: 2000;
      background: rgba(2, 6, 23, .72); backdrop-filter: blur(3px);
    }
    body.is-loading .loading-overlay { display: grid; }
    .loading-box { background: #172033; border: 1px solid #3b4a63; border-radius: .5rem; padding: 1.25rem 1.5rem; min-width: 18rem; text-align: center; }
    footer { color: #c7d2fe; border-top: 1px solid #273449; background: linear-gradient(90deg, #121b2d, #172033 45%, #13251f); }
    .footer-pill { border: 1px solid #334155; border-radius: 999px; padding: .35rem .75rem; background: rgba(15, 23, 42, .55); }
    .icon-muted { color: #8bb4ff; }
  </style>
</head>
<body class="min-vh-100 d-flex flex-column">
{% if session.get("admin") %}
<nav class="navbar navbar-expand-lg navbar-dark sticky-top">
  <div class="container-fluid">
    <a class="navbar-brand fw-semibold" href="{{ url_for('dashboard') }}"><i class="fa-solid fa-brain me-2 icon-muted"></i>BrainClaw Admin</a>
    <div class="navbar-nav">
      <a class="nav-link" href="{{ url_for('dashboard') }}"><i class="fa-solid fa-robot me-1"></i>Agents</a>
      <a class="nav-link" href="{{ url_for('memories') }}"><i class="fa-solid fa-layer-group me-1"></i>Memories</a>
      <a class="nav-link" href="{{ url_for('ingest') }}"><i class="fa-solid fa-file-circle-plus me-1"></i>Ingest</a>
      <a class="nav-link" href="{{ url_for('query') }}"><i class="fa-solid fa-terminal me-1"></i>SQL Query</a>
      <a class="nav-link" href="{{ url_for('backup_restore') }}"><i class="fa-solid fa-box-archive me-1"></i>Backup</a>
      <a class="nav-link" href="{{ url_for('api_keys') }}"><i class="fa-solid fa-key me-1"></i>API Keys</a>
    </div>
    <form method="post" action="{{ url_for('logout') }}" class="ms-auto">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <button class="btn btn-sm btn-outline-light"><i class="fa-solid fa-right-from-bracket me-1"></i>Sign out</button>
    </form>
  </div>
</nav>
{% endif %}
<main class="container-fluid py-4 flex-grow-1">
  {{ body|safe }}
</main>
{% set flash_messages = get_flashed_messages(with_categories=true) %}
<div id="flashModal" class="modal fade" tabindex="-1" aria-labelledby="flashModalTitle" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content panel">
      <div class="modal-header">
        <h5 class="modal-title" id="flashModalTitle"><i id="flashModalIcon" class="fa-solid fa-circle-info me-2 icon-muted"></i><span id="flashModalHeading">Message</span></h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body" id="flashModalBody"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-primary" data-bs-dismiss="modal">OK</button>
      </div>
    </div>
  </div>
</div>
<div id="confirmModal" class="modal fade" tabindex="-1" aria-labelledby="confirmModalTitle" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content panel">
      <div class="modal-header">
        <h5 class="modal-title" id="confirmModalTitle"><i class="fa-solid fa-triangle-exclamation me-2 text-warning"></i>Confirm action</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body" id="confirmModalBody"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline-light" data-bs-dismiss="modal">Cancel</button>
        <button type="button" class="btn btn-danger" id="confirmModalSubmit"><i class="fa-solid fa-check me-1"></i>Confirm</button>
      </div>
    </div>
  </div>
</div>
{% if created_key is defined and created_key %}
<div id="createdKeyModal" class="modal fade" tabindex="-1" aria-labelledby="createdKeyModalTitle" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content panel">
      <div class="modal-header">
        <h5 class="modal-title" id="createdKeyModalTitle"><i class="fa-solid fa-key me-2 text-warning"></i>API key created</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <p class="text-secondary">This key is available from the API keys table while it remains stored.</p>
        <div class="secret-box p-3 rounded border border-warning-subtle bg-dark text-warning" data-secret-value>{{ created_key }}</div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-outline-light" data-copy-secret="{{ created_key }}"><i class="fa-solid fa-copy me-1"></i>Copy</button>
        <button type="button" class="btn btn-primary" data-bs-dismiss="modal">Done</button>
      </div>
    </div>
  </div>
</div>
{% endif %}
<div class="loading-overlay" aria-live="polite" aria-busy="true">
  <div class="loading-box shadow">
    <div class="spinner-border text-info mb-3" role="status"></div>
    <div class="fw-semibold">Working on it</div>
    <div class="text-secondary small">Large uploads and embedding can take a moment.</div>
  </div>
</div>
<footer class="container-fluid py-3 small">
  <div class="d-flex flex-column flex-lg-row align-items-start align-items-lg-center justify-content-between gap-3">
    <div class="d-flex align-items-center gap-2">
      <span class="footer-pill"><i class="fa-solid fa-shield-halved me-1"></i>Local-first admin</span>
      <span class="footer-pill"><i class="fa-solid fa-database me-1"></i>SQLite + FAISS</span>
      <a class="footer-pill text-decoration-none text-reset" href="https://github.com/ibsoft/brainclaw" target="_blank" rel="noopener noreferrer"><i class="fa-brands fa-github me-1"></i>ibsoft/brainclaw</a>
    </div>
    <div class="text-lg-end text-secondary">
      <i class="fa-solid fa-lock me-1"></i>Bind to localhost unless TLS, firewalling, and operational controls are in place.
    </div>
  </div>
</footer>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
  const flashMessages = {{ flash_messages|tojson }};
  const flashMeta = {
    success: { heading: "Success", icon: "fa-circle-check", color: "text-success" },
    danger: { heading: "Error", icon: "fa-triangle-exclamation", color: "text-danger" },
    error: { heading: "Error", icon: "fa-triangle-exclamation", color: "text-danger" },
    warning: { heading: "Warning", icon: "fa-circle-exclamation", color: "text-warning" },
    info: { heading: "Information", icon: "fa-circle-info", color: "text-info" },
    message: { heading: "Information", icon: "fa-circle-info", color: "text-info" }
  };
  let pendingConfirmedForm = null;

  function showLoadingForForm(form) {
    document.body.classList.add("is-loading");
    for (const button of form.querySelectorAll("button[type='submit'], button:not([type])")) {
      button.disabled = true;
      if (!button.dataset.originalHtml) button.dataset.originalHtml = button.innerHTML;
      button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Working';
    }
  }

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.dataset.noSpinner === "true") return;
    if (form.dataset.confirm && form !== pendingConfirmedForm) {
      event.preventDefault();
      const body = document.getElementById("confirmModalBody");
      const submit = document.getElementById("confirmModalSubmit");
      body.textContent = form.dataset.confirm;
      submit.onclick = () => {
        pendingConfirmedForm = form;
        bootstrap.Modal.getOrCreateInstance(document.getElementById("confirmModal")).hide();
        showLoadingForForm(form);
        form.requestSubmit();
      };
      bootstrap.Modal.getOrCreateInstance(document.getElementById("confirmModal")).show();
      return;
    }
    showLoadingForForm(form);
  });
  function syncIngestFields() {
    const type = document.querySelector("[data-ingest-type]");
    if (!type) return;
    const isDocument = type.value === "document";
    for (const element of document.querySelectorAll("[data-note-fields]")) {
      element.classList.toggle("d-none", isDocument);
      for (const input of element.querySelectorAll("input, textarea, select")) input.disabled = isDocument;
    }
    for (const element of document.querySelectorAll("[data-document-fields]")) {
      element.classList.toggle("d-none", !isDocument);
      for (const input of element.querySelectorAll("input, textarea, select")) input.disabled = !isDocument;
    }
  }
  document.addEventListener("change", (event) => {
    if (event.target && event.target.matches("[data-ingest-type]")) syncIngestFields();
  });
  document.addEventListener("DOMContentLoaded", syncIngestFields);
  document.addEventListener("DOMContentLoaded", () => {
    const createdKeyModal = document.getElementById("createdKeyModal");
    if (createdKeyModal) bootstrap.Modal.getOrCreateInstance(createdKeyModal).show();
  });
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-secret]");
    if (!button) return;
    const secret = button.dataset.copySecret || "";
    if (!secret) return;
    const originalHtml = button.innerHTML;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(secret);
      } else {
        const input = document.createElement("textarea");
        input.value = secret;
        input.setAttribute("readonly", "");
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.appendChild(input);
        input.select();
        document.execCommand("copy");
        input.remove();
      }
      button.innerHTML = '<i class="fa-solid fa-check me-1"></i>Copied';
      window.setTimeout(() => { button.innerHTML = originalHtml; }, 1500);
    } catch {
      button.innerHTML = '<i class="fa-solid fa-triangle-exclamation me-1"></i>Copy failed';
      window.setTimeout(() => { button.innerHTML = originalHtml; }, 1800);
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    if (!flashMessages.length) return;
    const modalElement = document.getElementById("flashModal");
    const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
    const icon = document.getElementById("flashModalIcon");
    const heading = document.getElementById("flashModalHeading");
    const body = document.getElementById("flashModalBody");
    let index = 0;
    let timer = null;
    function showNextFlash() {
      if (index >= flashMessages.length) return;
      const [category, message] = flashMessages[index++];
      const meta = flashMeta[category] || flashMeta.info;
      icon.className = `fa-solid ${meta.icon} me-2 ${meta.color}`;
      heading.textContent = meta.heading;
      body.textContent = message;
      modal.show();
      window.clearTimeout(timer);
      timer = window.setTimeout(() => modal.hide(), 7000);
    }
    modalElement.addEventListener("hidden.bs.modal", showNextFlash);
    showNextFlash();
  });
  document.addEventListener("DOMContentLoaded", () => {
    for (const row of document.querySelectorAll("[data-memory-modal-target]")) {
      row.addEventListener("dblclick", (event) => {
        if (event.target.closest("a, button, form, input, textarea, select")) return;
        const modalId = row.dataset.memoryModalTarget;
        const modalElement = document.getElementById(modalId);
        if (modalElement) bootstrap.Modal.getOrCreateInstance(modalElement).show();
      });
    }
  });
</script>
</body>
</html>
"""

BLOCKED_SQL_WORDS = re.compile(
    r"\b(attach|alter|analyze|create|delete|detach|drop|insert|pragma|reindex|replace|update|vacuum)\b",
    re.IGNORECASE,
)
BLOCKED_SQL_IDENTIFIERS = re.compile(r"\b(app_settings|key_hash|key_secret|password_hash)\b", re.IGNORECASE)
HIDDEN_RESULT_COLUMNS = {"key_hash", "key_secret", "password_hash", "admin_password_hash"}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")
PASSWORD_SPECIAL_PATTERN = re.compile(r"[^A-Za-z0-9]")
DEFAULT_PAGE_SIZE = 50
BACKUP_MANIFEST = "brainclaw-backup.json"
BACKUP_MAX_UPLOAD_BYTES = 512 * 1024 * 1024


def clean_form_text(value: str | None, max_len: int = 256) -> str:
    return " ".join((value or "").strip().split())[:max_len]


def safe_zip_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if not members:
        raise ValueError("Backup archive is empty.")
    for member in members:
        target = Path(member.filename)
        if member.filename.startswith("/") or ".." in target.parts:
            raise ValueError("Backup archive contains an unsafe path.")
    return members


def server_backup_dir(settings: Any) -> Path:
    path = Path(settings.data_dir) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_backup_name(filename: str) -> str:
    name = Path(filename).name
    if not re.fullmatch(r"brainclaw-backup-[0-9TZ]+\.zip", name):
        raise ValueError("Invalid backup filename.")
    return name


def backup_file_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "size_bytes": stat.st_size,
        "size_mb": stat.st_size / (1024 * 1024),
        "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def list_server_backups(settings: Any) -> list[dict[str, Any]]:
    backup_dir = server_backup_dir(settings)
    return [backup_file_info(path) for path in sorted(backup_dir.glob("brainclaw-backup-*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)]


def zip_directory(zip_file: zipfile.ZipFile, root: Path, prefix: str, exclude: set[Path] | None = None) -> None:
    if not root.exists():
        return
    exclude = {path.resolve() for path in (exclude or set())}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        resolved = path.resolve()
        if any(resolved == excluded or excluded in resolved.parents for excluded in exclude):
            continue
        if path.suffix in {".tmp", ".bak"}:
            continue
        arcname = Path(prefix) / path.relative_to(root)
        zip_file.write(path, arcname.as_posix())


def sqlite_backup_bytes(sqlite_path: Path) -> bytes:
    buffer = io.BytesIO()
    with tempfile.NamedTemporaryFile(suffix=".sqlite3") as tmp:
        source = sqlite3.connect(sqlite_path)
        try:
            destination = sqlite3.connect(tmp.name)
            try:
                source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()
        tmp.seek(0)
        buffer.write(tmp.read())
    return buffer.getvalue()


def create_backup_file(settings: Any) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = server_backup_dir(settings) / f"brainclaw-backup-{timestamp}.zip"
    data_dir = Path(settings.data_dir)
    sqlite_path = Path(settings.sqlite_path)
    exclude = {
        sqlite_path,
        sqlite_path.with_name(sqlite_path.name + "-wal"),
        sqlite_path.with_name(sqlite_path.name + "-shm"),
        server_backup_dir(settings),
    }
    manifest = {
        "app": settings.app_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": "brainclaw-data-backup-v1",
        "sqlite_path": f"data/{sqlite_path.name}",
        "embedding_model_name": settings.embedding_model_name,
        "isolate_indexes": settings.isolate_indexes,
    }
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(BACKUP_MANIFEST, json.dumps(manifest, indent=2))
        if sqlite_path.exists():
            zip_file.writestr(f"data/{sqlite_path.name}", sqlite_backup_bytes(sqlite_path))
        zip_directory(zip_file, data_dir, "data", exclude=exclude)
    return backup_path


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def reset_live_app_data(settings: Any) -> None:
    project_root = Path(__file__).resolve().parent.parent
    data_dir = Path(settings.data_dir).resolve()
    backup_dir = server_backup_dir(settings).resolve()
    explicit_paths = [
        Path(settings.sqlite_path),
        Path(settings.sqlite_path).with_name(Path(settings.sqlite_path).name + "-wal"),
        Path(settings.sqlite_path).with_name(Path(settings.sqlite_path).name + "-shm"),
        Path(settings.faiss_index_path),
        Path(settings.id_map_path),
        Path(settings.index_dir),
        Path(settings.upload_dir),
    ]

    if data_dir == project_root:
        raise ValueError("DATA_DIR cannot be the project root when resetting the app.")
    for path in explicit_paths:
        if path.resolve() == project_root:
            raise ValueError(f"Refusing to reset project root path: {path}")

    if data_dir.exists():
        for item in data_dir.iterdir():
            resolved = item.resolve()
            if resolved == backup_dir or backup_dir in resolved.parents:
                continue
            remove_path(item)

    for path in explicit_paths:
        resolved = path.resolve()
        if resolved == backup_dir or backup_dir in resolved.parents:
            continue
        remove_path(path)

    data_dir.mkdir(parents=True, exist_ok=True)
    Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.index_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


def validate_username(username: str) -> str:
    cleaned = clean_form_text(username, 64)
    if not USERNAME_PATTERN.fullmatch(cleaned):
        raise ValueError("Username must be 3-64 characters and may contain letters, numbers, dot, dash, underscore, or @.")
    return cleaned


def validate_admin_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")
    if len(password) > 256:
        raise ValueError("Password is too long.")
    if not any(char.islower() for char in password):
        raise ValueError("Password must include a lowercase letter.")
    if not any(char.isupper() for char in password):
        raise ValueError("Password must include an uppercase letter.")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must include a number.")
    if not PASSWORD_SPECIAL_PATTERN.search(password):
        raise ValueError("Password must include a symbol.")


def create_admin_app(settings: Any, db: Database, memory_service: MemoryService, file_service: FileService, faiss_store: FaissStore) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.admin_session_secret or settings.memory_api_key or secrets.token_urlsafe(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=max(settings.max_upload_bytes + 64 * 1024, BACKUP_MAX_UPLOAD_BYTES),
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    @app.after_request
    def security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.context_processor
    def inject_csrf():
        def csrf_token() -> str:
            token = session.get("csrf_token")
            if not token:
                token = secrets.token_urlsafe(32)
                session["csrf_token"] = token
            return token

        return {"csrf_token": csrf_token}

    def render(title: str, body: str, **context: Any) -> str:
        rendered_body = render_template_string(body, **context)
        return render_template_string(BASE_TEMPLATE, title=title, body=Markup(rendered_body))

    def login_required(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not db.admin_is_configured():
                return redirect(url_for("setup"))
            if not session.get("admin"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    def validate_csrf() -> bool:
        return bool(session.get("csrf_token")) and secrets.compare_digest(
            str(session.get("csrf_token")),
            str(request.values.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")),
        )

    def validate_sql(sql: str) -> str:
        normalized = sql.strip()
        if not normalized:
            raise ValueError("SQL is required.")
        if len(normalized) > 8_000:
            raise ValueError("SQL is too long.")
        if normalized.endswith(";"):
            normalized = normalized[:-1].strip()
        if ";" in normalized:
            raise ValueError("Only one SQL statement is allowed.")
        first_word = normalized.split(None, 1)[0].lower()
        if first_word not in {"select", "with"}:
            raise ValueError("Only SELECT and WITH queries are allowed.")
        if BLOCKED_SQL_WORDS.search(normalized):
            raise ValueError("This query contains a blocked SQL keyword.")
        if BLOCKED_SQL_IDENTIFIERS.search(normalized):
            raise ValueError("This query references an internal credential field or table.")
        return normalized

    def available_scopes() -> list[dict[str, Any]]:
        return [dict(row) for row in db.list_scopes()]

    def selected_scopes(scope_mode: str, agent_id: str | None, workspace: str | None) -> list[dict[str, str]]:
        if scope_mode == "all":
            scopes = available_scopes()
            if not scopes:
                raise ValueError("No existing agents/workspaces are available for all-agent ingest.")
            return [{"agent_id": str(scope["agent_id"]), "workspace": str(scope["workspace"])} for scope in scopes]
        if not agent_id or not workspace:
            raise ValueError("Agent and workspace are required for single-agent ingest.")
        return [{"agent_id": agent_id, "workspace": workspace}]

    def page_param(name: str = "page") -> int:
        return max(1, int(request.values.get(name, "1") or "1"))

    def per_page_param(name: str = "per_page") -> int:
        return min(200, max(1, int(request.values.get(name, str(DEFAULT_PAGE_SIZE)) or str(DEFAULT_PAGE_SIZE))))

    def paginate_list(items: list[Any], page: int, per_page: int) -> tuple[list[Any], int, int]:
        total = len(items)
        pages = max(1, math.ceil(total / per_page))
        safe_page = min(max(1, page), pages)
        start = (safe_page - 1) * per_page
        return items[start : start + per_page], total, pages

    def admin_redirect_target(next_path: str | None) -> str:
        if not next_path or not next_path.startswith("/") or next_path.startswith("//"):
            return url_for("dashboard")
        return f"{request.script_root}{next_path}"

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if db.admin_is_configured():
            return redirect(url_for("login"))
        if session.get("admin"):
            session.clear()
        if request.method == "POST":
            if not validate_csrf():
                flash("Invalid session token.", "danger")
            else:
                username = clean_form_text(request.form.get("username"), 64)
                password = request.form.get("password") or ""
                confirm_password = request.form.get("confirm_password") or ""
                try:
                    username = validate_username(username)
                    validate_admin_password(password)
                    if password != confirm_password:
                        raise ValueError("Passwords do not match.")
                    db.set_admin_credentials(username, generate_password_hash(password, method="scrypt"))
                    session.clear()
                    session["admin"] = True
                    session["admin_username"] = username
                    session["csrf_token"] = secrets.token_urlsafe(32)
                    flash("Admin account created.", "success")
                    return redirect(url_for("dashboard"))
                except ValueError as exc:
                    flash(str(exc), "danger")
        return render(
            "Setup",
            """
            <div class="auth-shell">
              <div class="auth-card">
                <div class="panel p-4 shadow">
                  <h1 class="h4 mb-3"><i class="fa-solid fa-user-shield me-2 icon-muted"></i>Create Admin Account</h1>
                  <p class="text-secondary">This one-time setup stores a hashed admin password in SQLite.</p>
                  <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <div class="mb-3">
                      <label class="form-label"><i class="fa-solid fa-user me-1"></i>Username</label>
                      <input class="form-control" name="username" autocomplete="username" value="{{ default_username }}" minlength="3" maxlength="64" pattern="[A-Za-z0-9_.@-]{3,64}" required>
                    </div>
                    <div class="mb-3">
                      <label class="form-label"><i class="fa-solid fa-lock me-1"></i>Password</label>
                      <input class="form-control" type="password" name="password" autocomplete="new-password" minlength="12" maxlength="256" required>
                      <div class="form-text">Use at least 12 characters with uppercase, lowercase, number, and symbol.</div>
                    </div>
                    <div class="mb-3">
                      <label class="form-label"><i class="fa-solid fa-check-double me-1"></i>Confirm password</label>
                      <input class="form-control" type="password" name="confirm_password" autocomplete="new-password" minlength="12" maxlength="256" required>
                    </div>
                    <button class="btn btn-primary w-100"><i class="fa-solid fa-circle-check me-1"></i>Create admin</button>
                  </form>
                </div>
              </div>
            </div>
            """,
            default_username=settings.admin_username,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not db.admin_is_configured():
            return redirect(url_for("setup"))
        if request.method == "POST":
            username, password_hash = db.get_admin_credentials()
            if not validate_csrf():
                flash("Invalid session token.", "danger")
            elif clean_form_text(request.form.get("username"), 64) == username and password_hash and check_password_hash(password_hash, request.form.get("password", "")):
                session.clear()
                session["admin"] = True
                session["admin_username"] = username
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(admin_redirect_target(request.args.get("next")))
            else:
                flash("Invalid username or password.", "danger")
        return render(
            "Login",
            """
            <div class="auth-shell">
              <div class="auth-card">
                <div class="panel p-4 shadow">
                  <h1 class="h4 mb-3"><i class="fa-solid fa-brain me-2 icon-muted"></i>BrainClaw Admin</h1>
                  <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <div class="mb-3">
                      <label class="form-label"><i class="fa-solid fa-user me-1"></i>Username</label>
                      <input class="form-control" name="username" autocomplete="username" minlength="3" maxlength="64" pattern="[A-Za-z0-9_.@-]{3,64}" required>
                    </div>
                    <div class="mb-3">
                      <label class="form-label"><i class="fa-solid fa-lock me-1"></i>Password</label>
                      <input class="form-control" type="password" name="password" autocomplete="current-password" maxlength="256" required>
                    </div>
                    <button class="btn btn-primary w-100"><i class="fa-solid fa-right-to-bracket me-1"></i>Sign in</button>
                  </form>
                </div>
              </div>
            </div>
            """,
        )

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        if not validate_csrf():
            flash("Invalid session token.", "danger")
            return redirect(url_for("dashboard"))
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        page = page_param()
        per_page = per_page_param()
        all_scopes = [dict(row) for row in db.list_scopes()]
        for scope in all_scopes:
            scope["vectors"] = faiss_store.vector_count_for_scope(scope["agent_id"], scope["workspace"])
        scopes, total, pages = paginate_list(all_scopes, page, per_page)
        return render(
            "Agents",
            """
            <div class="d-flex align-items-center justify-content-between mb-3">
              <h1 class="h3 mb-0"><i class="fa-solid fa-robot me-2 icon-muted"></i>Agents</h1>
              <div class="d-flex align-items-center gap-2">
                <span class="badge text-bg-secondary">{{ total }} total</span>
                <a class="btn btn-primary" href="{{ url_for('api_keys') }}"><i class="fa-solid fa-key me-1"></i>Manage API Keys</a>
              </div>
            </div>
            <div class="panel p-3">
              <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                  <thead><tr><th>Agent</th><th>Workspace</th><th class="text-end">Memories</th><th class="text-end">Files</th><th class="text-end">Vectors</th><th></th></tr></thead>
                  <tbody>
                  {% for scope in scopes %}
                    <tr>
                      <td>{{ scope.agent_id }}</td>
                      <td>{{ scope.workspace }}</td>
                      <td class="text-end">{{ scope.memory_count }}</td>
                      <td class="text-end">{{ scope.file_count }}</td>
                      <td class="text-end">{{ scope.vectors }}</td>
                      <td class="text-end"><a class="btn btn-sm btn-outline-light" href="{{ url_for('memories', agent_id=scope.agent_id, workspace=scope.workspace) }}"><i class="fa-solid fa-eye me-1"></i>View</a></td>
                    </tr>
                  {% else %}
                    <tr><td colspan="6" class="text-center text-secondary py-4">No agents have stored memories yet.</td></tr>
                  {% endfor %}
                  </tbody>
                </table>
              </div>
              <nav class="mt-3">
                <ul class="pagination mb-0">
                  <li class="page-item {% if page <= 1 %}disabled{% endif %}"><a class="page-link" href="{{ page_url(page-1) }}">Previous</a></li>
                  <li class="page-item disabled"><span class="page-link">Page {{ page }} of {{ pages }} · {{ per_page }} rows</span></li>
                  <li class="page-item {% if page >= pages %}disabled{% endif %}"><a class="page-link" href="{{ page_url(page+1) }}">Next</a></li>
                </ul>
              </nav>
            </div>
            """,
            scopes=scopes,
            total=total,
            page=page,
            pages=pages,
            per_page=per_page,
            page_url=lambda p: url_for("dashboard", page=max(1, p), per_page=per_page),
        )

    @app.route("/backup", methods=["GET"])
    @login_required
    def backup_restore():
        data_dir = Path(settings.data_dir)
        sqlite_path = Path(settings.sqlite_path)
        index_dir = Path(settings.index_dir)
        upload_dir = Path(settings.upload_dir)
        backup_dir = server_backup_dir(settings)
        backups = list_server_backups(settings)
        return render(
            "Backup",
            """
            <div class="d-flex align-items-center justify-content-between mb-3">
              <div>
                <h1 class="h3 mb-1"><i class="fa-solid fa-box-archive me-2 icon-muted"></i>Backup and Restore</h1>
                <div class="text-secondary">Export or restore the SQLite database, FAISS indexes, ID maps, and uploaded document storage.</div>
              </div>
              <form method="post" action="{{ url_for('create_backup') }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button class="btn btn-primary"><i class="fa-solid fa-box-archive me-1"></i>Create backup</button>
              </form>
            </div>

            <div class="row g-3">
              <div class="col-xl-6">
                <div class="panel p-3 h-100">
                  <h2 class="h5"><i class="fa-solid fa-database me-2 icon-muted"></i>Current data</h2>
                  <dl class="row mb-0">
                    <dt class="col-sm-4">Data directory</dt><dd class="col-sm-8 secret-box">{{ data_dir }}</dd>
                    <dt class="col-sm-4">SQLite</dt><dd class="col-sm-8 secret-box">{{ sqlite_path }}</dd>
                    <dt class="col-sm-4">Indexes</dt><dd class="col-sm-8 secret-box">{{ index_dir }}</dd>
                    <dt class="col-sm-4">Uploads</dt><dd class="col-sm-8 secret-box">{{ upload_dir }}</dd>
                    <dt class="col-sm-4">Server backups</dt><dd class="col-sm-8 secret-box">{{ backup_dir }}</dd>
                    <dt class="col-sm-4">Vectors</dt><dd class="col-sm-8">{{ vector_count }}</dd>
                  </dl>
                  <div class="border border-danger-subtle rounded p-2 mt-3">
                    <div class="d-flex align-items-center justify-content-between gap-2 mb-2">
                      <div>
                        <div class="fw-semibold text-danger"><i class="fa-solid fa-triangle-exclamation me-1"></i>Reset app</div>
                        <div class="small text-secondary">Keeps saved backup zips, removes live data, indexes, uploads, API keys, and admin credentials.</div>
                      </div>
                    </div>
                    <form method="post" action="{{ url_for('purge_data') }}" data-confirm="Permanently reset BrainClaw? Download a backup first.">
                      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                      <div class="input-group input-group-sm">
                        <input class="form-control" name="confirmation" placeholder="Type PURGE" autocomplete="off">
                        <button class="btn btn-outline-danger"><i class="fa-solid fa-rotate-left me-1"></i>Reset</button>
                      </div>
                    </form>
                  </div>
                </div>
              </div>
              <div class="col-xl-6">
                <div class="panel p-3 h-100">
                  <h2 class="h5"><i class="fa-solid fa-file-zipper me-2 icon-muted"></i>Restore backup</h2>
                  <p class="text-secondary">Restore a BrainClaw backup zip into this instance. This replaces the current data directory.</p>
                  <form method="post" action="{{ url_for('restore_backup') }}" enctype="multipart/form-data" data-confirm="Restore this backup and replace all current BrainClaw data?">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <input class="form-control mb-3" type="file" name="backup_file" accept=".zip" required>
                    <button class="btn btn-warning"><i class="fa-solid fa-upload me-1"></i>Restore backup</button>
                  </form>
                </div>
              </div>
              <div class="col-12">
                <div class="panel p-3">
                  <div class="d-flex align-items-center justify-content-between mb-2">
                    <h2 class="h5 mb-0"><i class="fa-solid fa-clock-rotate-left me-2 icon-muted"></i>Saved backups</h2>
                    <span class="badge text-bg-secondary">{{ backups|length }} files</span>
                  </div>
                  <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                      <thead><tr><th>Backup file</th><th>Created</th><th class="text-end">Size</th><th class="text-end">Actions</th></tr></thead>
                      <tbody>
                      {% for backup in backups %}
                        <tr>
                          <td class="secret-box">{{ backup.name }}</td>
                          <td>{{ backup.created_at }}</td>
                          <td class="text-end">{{ "%.2f"|format(backup.size_mb) }} MB</td>
                          <td class="text-end">
                            <a class="btn btn-sm btn-outline-light" href="{{ url_for('get_backup', filename=backup.name) }}"><i class="fa-solid fa-download me-1"></i>Download</a>
                            <form class="d-inline" method="post" action="{{ url_for('delete_backup', filename=backup.name) }}" data-confirm="Delete this backup zip from disk?">
                              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                              <button class="btn btn-sm btn-outline-danger"><i class="fa-solid fa-trash me-1"></i>Delete</button>
                            </form>
                          </td>
                        </tr>
                      {% else %}
                        <tr><td colspan="4" class="text-center text-secondary py-4">No server-side backups saved yet.</td></tr>
                      {% endfor %}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
            """,
            data_dir=data_dir,
            sqlite_path=sqlite_path,
            index_dir=index_dir,
            upload_dir=upload_dir,
            backup_dir=backup_dir,
            backups=backups,
            vector_count=faiss_store.vector_count,
        )

    @app.route("/backup/create", methods=["POST"])
    @login_required
    def create_backup():
        if not validate_csrf():
            flash("Invalid session token.", "danger")
            return redirect(url_for("backup_restore"))
        try:
            backup_path = create_backup_file(settings)
            flash(f"Backup saved on server: {backup_path.name}", "success")
        except Exception as exc:
            flash(f"Backup failed: {escape(str(exc))}", "danger")
        return redirect(url_for("backup_restore"))

    @app.route("/backup/files/<path:filename>", methods=["GET"])
    @login_required
    def get_backup(filename: str):
        try:
            backup_name = safe_backup_name(filename)
            backup_path = server_backup_dir(settings) / backup_name
            if not backup_path.exists() or not backup_path.is_file():
                raise ValueError("Backup file was not found.")
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("backup_restore"))
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=backup_path.name,
            mimetype="application/zip",
        )

    @app.route("/backup/files/<path:filename>/delete", methods=["POST"])
    @login_required
    def delete_backup(filename: str):
        if not validate_csrf():
            flash("Invalid session token.", "danger")
            return redirect(url_for("backup_restore"))
        try:
            backup_name = safe_backup_name(filename)
            backup_path = server_backup_dir(settings) / backup_name
            if not backup_path.exists() or not backup_path.is_file():
                raise ValueError("Backup file was not found.")
            backup_path.unlink()
            flash(f"Deleted backup: {backup_name}", "success")
        except Exception as exc:
            flash(f"Delete failed: {escape(str(exc))}", "danger")
        return redirect(url_for("backup_restore"))

    @app.route("/backup/restore", methods=["POST"])
    @login_required
    def restore_backup():
        if not validate_csrf():
            flash("Invalid session token.", "danger")
            return redirect(url_for("backup_restore"))
        backup_file = request.files.get("backup_file")
        if backup_file is None or not backup_file.filename:
            flash("Backup zip is required.", "danger")
            return redirect(url_for("backup_restore"))
        try:
            with tempfile.TemporaryDirectory(prefix="brainclaw-restore-") as tmpdir:
                tmp_path = Path(tmpdir)
                archive_path = tmp_path / "backup.zip"
                backup_file.save(archive_path)
                with zipfile.ZipFile(archive_path) as archive:
                    safe_zip_members(archive)
                    if BACKUP_MANIFEST not in archive.namelist():
                        raise ValueError("Backup manifest is missing.")
                    archive.extractall(tmp_path / "extract")
                restored_data = tmp_path / "extract" / "data"
                if not restored_data.exists() or not restored_data.is_dir():
                    raise ValueError("Backup does not contain a data directory.")
                data_dir = Path(settings.data_dir)
                backup_dir = server_backup_dir(settings)
                preserved_backups = tmp_path / "preserved-backups"
                if backup_dir.exists():
                    shutil.copytree(backup_dir, preserved_backups)
                if data_dir.exists():
                    shutil.rmtree(data_dir)
                shutil.copytree(restored_data, data_dir)
                if preserved_backups.exists():
                    restored_backup_dir = server_backup_dir(settings)
                    if restored_backup_dir.exists():
                        shutil.rmtree(restored_backup_dir)
                    shutil.copytree(preserved_backups, restored_backup_dir)
                Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
                Path(settings.index_dir).mkdir(parents=True, exist_ok=True)
                Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
            db.init_schema()
            faiss_store.reload()
            session.clear()
            flash("Backup restored. BrainClaw data and FAISS indexes were reloaded. Sign in with the restored admin account.", "success")
            return redirect(url_for("login" if db.admin_is_configured() else "setup"))
        except Exception as exc:
            flash(f"Restore failed: {escape(str(exc))}", "danger")
        return redirect(url_for("backup_restore"))

    @app.route("/backup/purge", methods=["POST"])
    @login_required
    def purge_data():
        if not validate_csrf():
            flash("Invalid session token.", "danger")
            return redirect(url_for("backup_restore"))
        if request.form.get("confirmation") != "PURGE":
            flash("Type PURGE to confirm data purge.", "warning")
            return redirect(url_for("backup_restore"))
        reset_live_app_data(settings)
        db.init_schema()
        faiss_store.reload()
        session.clear()
        flash("BrainClaw was reset. Create a new admin account to continue.", "warning")
        return redirect(url_for("setup"))

    @app.route("/query", methods=["GET", "POST"])
    @login_required
    def query():
        sql = request.form.get("sql") if request.method == "POST" else request.args.get("sql")
        sql = sql or "SELECT id, agent_id, workspace, source, memory_type, importance, updated_at FROM memories WHERE deleted = 0 ORDER BY updated_at DESC LIMIT 25"
        columns: list[str] = []
        rows: list[dict[str, Any]] = []
        total = 0
        page = page_param()
        per_page = per_page_param()
        pages = 1
        should_run = request.method == "POST" or bool(request.args.get("sql"))
        if should_run:
            if not validate_csrf():
                flash("Invalid session token.", "danger")
            else:
                try:
                    safe_sql = validate_sql(sql)
                    columns, rows, total = db.execute_readonly_query_page(safe_sql, per_page, (page - 1) * per_page)
                    columns = [column for column in columns if column.lower() not in HIDDEN_RESULT_COLUMNS]
                    pages = max(1, math.ceil(total / per_page))
                    flash(f"Query returned {total} rows.", "success")
                except Exception as exc:
                    flash(f"Query rejected: {escape(str(exc))}", "danger")
        return render(
            "SQL Query",
            """
            <div class="row g-3">
              <div class="col-xl-8">
                <div class="panel p-3">
                  <div class="d-flex align-items-center justify-content-between mb-3">
                    <h1 class="h3 mb-0"><i class="fa-solid fa-terminal me-2 icon-muted"></i>SQL Query</h1>
                    <span class="badge text-bg-secondary">read only</span>
                  </div>
                  <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <input type="hidden" name="per_page" value="{{ per_page }}">
                    <textarea class="form-control sql-editor mb-3" name="sql" spellcheck="false">{{ sql }}</textarea>
                    <button class="btn btn-primary"><i class="fa-solid fa-play me-1"></i>Run query</button>
                  </form>
                </div>
                {% if columns %}
                <div class="panel p-3 mt-3">
                  <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                      <thead><tr>{% for column in columns %}<th>{{ column }}</th>{% endfor %}</tr></thead>
                      <tbody>
                      {% for row in rows %}
                        <tr>{% for column in columns %}<td class="content-cell" title="{{ row[column] }}">{{ row[column] }}</td>{% endfor %}</tr>
                      {% endfor %}
                      </tbody>
                    </table>
                  </div>
                  <nav class="mt-3">
                    <ul class="pagination mb-0">
                      <li class="page-item {% if page <= 1 %}disabled{% endif %}"><a class="page-link" href="{{ page_url(page-1) }}">Previous</a></li>
                      <li class="page-item disabled"><span class="page-link">Page {{ page }} of {{ pages }} · {{ per_page }} rows</span></li>
                      <li class="page-item {% if page >= pages %}disabled{% endif %}"><a class="page-link" href="{{ page_url(page+1) }}">Next</a></li>
                    </ul>
                  </nav>
                </div>
                {% endif %}
              </div>
              <div class="col-xl-4">
                <div class="panel p-3">
                  <h2 class="h4"><i class="fa-solid fa-book me-2 icon-muted"></i>BrainQL</h2>
                  <p class="text-secondary">BrainQL is read-only SQLite SELECT over BrainClaw tables. Use it for inspection and reporting, not mutation.</p>
                  <h3 class="h6">Allowed</h3>
                  <ul class="small">
                    <li>Single <code>SELECT</code> or <code>WITH</code> statement</li>
                    <li>Joins, grouping, ordering, filtering, and limits</li>
                    <li>Built-in SQLite scalar and aggregate functions</li>
                  </ul>
                  <h3 class="h6">Blocked</h3>
                  <ul class="small">
                    <li><code>INSERT</code>, <code>UPDATE</code>, <code>DELETE</code>, <code>DROP</code>, <code>ALTER</code>, <code>CREATE</code></li>
                    <li><code>PRAGMA</code>, <code>ATTACH</code>, <code>DETACH</code>, <code>VACUUM</code>, multiple statements</li>
                    <li>Results are capped at 200 rows in the admin UI</li>
                  </ul>
                  <h3 class="h6">Useful Tables</h3>
                  <div class="small">
                    <code>memories</code>, <code>chunks</code>, <code>files</code>, <code>file_chunks</code>, <code>api_keys</code>
                  </div>
                  <h3 class="h6 mt-3">Examples</h3>
                  <pre class="small secret-box text-secondary">SELECT agent_id, workspace, COUNT(*) AS memories
FROM memories
WHERE deleted = 0
GROUP BY agent_id, workspace;</pre>
                  <pre class="small secret-box text-secondary">SELECT m.id, m.agent_id, m.workspace, c.text
FROM chunks c
JOIN memories m ON m.id = c.memory_id
WHERE m.deleted = 0 AND c.deleted = 0
  AND c.text LIKE '%security%'
LIMIT 50;</pre>
                </div>
              </div>
            </div>
            """,
            sql=sql,
            columns=columns,
            rows=rows,
            total=total,
            page=page,
            pages=pages,
            per_page=per_page,
            page_url=lambda p: url_for("query", sql=sql, page=max(1, p), per_page=per_page, csrf_token=session.get("csrf_token", "")),
        )

    @app.route("/ingest", methods=["GET", "POST"])
    @login_required
    def ingest():
        per_page = per_page_param()
        scope_page = page_param("scope_page")
        memory_page = page_param("memory_page")
        file_page = page_param("file_page")
        all_scopes = available_scopes()
        scopes, scope_total, scope_pages = paginate_list(all_scopes, scope_page, per_page)
        recent_memories, memory_total = db.list_memories(None, None, None, per_page, (memory_page - 1) * per_page)
        memory_pages = max(1, math.ceil(memory_total / per_page))
        all_files = [dict(row) for row in db.list_files(limit=10_000)]
        recent_files, file_total, file_pages = paginate_list(all_files, file_page, per_page)
        if request.method == "POST":
            if not validate_csrf():
                flash("Invalid session token.", "danger")
            else:
                try:
                    ingest_type = request.form.get("ingest_type") or "note"
                    scope_mode = request.form.get("scope_mode") or "single"
                    agent_id = clean_form_text(request.form.get("agent_id"), 128) or None
                    workspace = clean_form_text(request.form.get("workspace"), 256) or None
                    source = clean_form_text(request.form.get("source"), 256) or ("admin-note" if ingest_type == "note" else "admin-upload")
                    raw_tags = clean_form_text(request.form.get("tags"), 1024)
                    targets = selected_scopes(scope_mode, agent_id, workspace)

                    if ingest_type == "note":
                        content = (request.form.get("content") or "").strip()
                        memory_type = clean_form_text(request.form.get("memory_type"), 64) or "note"
                        importance = float(request.form.get("importance") or "0.5")
                        tags = parse_tags(raw_tags)
                        if not content:
                            raise ValueError("Note content is required.")
                        created_ids = []
                        for target in targets:
                            result = memory_service.add_memory(
                                MemoryAddRequest(
                                    agent_id=target["agent_id"],
                                    workspace=target["workspace"],
                                    source=source,
                                    memory_type=memory_type,
                                    content=content,
                                    tags=tags,
                                    importance=importance,
                                )
                            )
                            created_ids.append(result["id"])
                        flash(f"Stored note in {len(targets)} scope(s): {created_ids}", "success")
                    elif ingest_type == "document":
                        upload = request.files.get("document")
                        if upload is None or not upload.filename:
                            raise ValueError("Document file is required.")
                        data = upload.read(settings.max_upload_bytes + 1)
                        created_ids = []
                        for target in targets:
                            result = file_service.ingest_file_bytes(
                                agent_id=target["agent_id"],
                                workspace=target["workspace"],
                                source=source,
                                raw_tags=raw_tags,
                                filename=upload.filename,
                                content_type=upload.content_type,
                                data=data,
                            )
                            created_ids.append(result["file_id"])
                        flash(f"Uploaded document into {len(targets)} scope(s): {created_ids}", "success")
                    else:
                        raise ValueError("Invalid ingest type.")
                except Exception as exc:
                    flash(f"Ingest failed: {escape(str(exc))}", "danger")
        return render(
            "Ingest",
            """
            <div class="d-flex align-items-center justify-content-between mb-3">
              <h1 class="h3 mb-0"><i class="fa-solid fa-file-circle-plus me-2 icon-muted"></i>Ingest</h1>
              <span class="badge text-bg-secondary">notes and documents</span>
            </div>
            <form class="panel p-3" method="post" enctype="multipart/form-data">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <div class="row g-3">
                <div class="col-lg-4">
                  <label class="form-label"><i class="fa-solid fa-route me-1"></i>Target</label>
                  <select class="form-select mb-2" name="scope_mode">
                    <option value="single">One agent/workspace</option>
                    <option value="all">All existing agents/workspaces</option>
                  </select>
                  <input class="form-control mb-2" name="agent_id" placeholder="Agent ID">
                  <input class="form-control" name="workspace" placeholder="Workspace">
                  <div class="form-text">For all-agent ingest, BrainClaw copies the same note or document into every existing scope.</div>
                </div>
                <div class="col-lg-4">
                  <label class="form-label"><i class="fa-solid fa-inbox me-1"></i>Type</label>
                  <select class="form-select mb-2" name="ingest_type" data-ingest-type>
                    <option value="note">Note to memory</option>
                    <option value="document">Document upload</option>
                  </select>
                  <input class="form-control mb-2" name="source" placeholder="Source, e.g. admin, docs, policy">
                  <input class="form-control" name="tags" placeholder="Tags, comma separated">
                </div>
                <div class="col-lg-4" data-note-fields>
                  <label class="form-label"><i class="fa-solid fa-sliders me-1"></i>Memory options</label>
                  <input class="form-control mb-2" name="memory_type" placeholder="Memory type" value="note">
                  <input class="form-control" name="importance" type="number" min="0" max="1" step="0.1" value="0.5">
                </div>
                <div class="col-lg-6" data-note-fields>
                  <label class="form-label"><i class="fa-solid fa-note-sticky me-1"></i>Note</label>
                  <textarea class="form-control sql-editor" name="content" placeholder="Write a note to store as memory"></textarea>
                </div>
                <div class="col-lg-6" data-document-fields>
                  <label class="form-label"><i class="fa-solid fa-file-arrow-up me-1"></i>Document</label>
                  <input class="form-control" type="file" name="document">
                  <div class="form-text">Supported: .txt .md .pdf .docx .csv .json .log .py .cs .js .yaml .yml .conf .service .html</div>
                </div>
              </div>
              <div class="d-flex justify-content-end mt-3">
                <button class="btn btn-primary"><i class="fa-solid fa-cloud-arrow-up me-1"></i>Ingest</button>
              </div>
            </form>
            <div class="panel p-3 mt-3">
              <h2 class="h5"><i class="fa-solid fa-bullseye me-2 icon-muted"></i>Available scopes</h2>
              <div class="text-secondary small mb-2">{{ scope_total }} total · {{ per_page }} rows per page</div>
              <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                  <thead><tr><th>Agent</th><th>Workspace</th><th class="text-end">Memories</th><th class="text-end">Files</th></tr></thead>
                  <tbody>
                  {% for scope in scopes %}
                    <tr><td>{{ scope.agent_id }}</td><td>{{ scope.workspace }}</td><td class="text-end">{{ scope.memory_count }}</td><td class="text-end">{{ scope.file_count }}</td></tr>
                  {% else %}
                    <tr><td colspan="4" class="text-center text-secondary py-4">No existing scopes yet. Use one-agent ingest and provide an agent/workspace.</td></tr>
                  {% endfor %}
                  </tbody>
                </table>
              </div>
              <nav class="mt-3">
                <ul class="pagination mb-0">
                  <li class="page-item {% if scope_page <= 1 %}disabled{% endif %}"><a class="page-link" href="{{ ingest_page_url(scope_page=scope_page-1) }}">Previous</a></li>
                  <li class="page-item disabled"><span class="page-link">Page {{ scope_page }} of {{ scope_pages }}</span></li>
                  <li class="page-item {% if scope_page >= scope_pages %}disabled{% endif %}"><a class="page-link" href="{{ ingest_page_url(scope_page=scope_page+1) }}">Next</a></li>
                </ul>
              </nav>
            </div>
            <div class="row g-3 mt-1">
              <div class="col-xl-7">
                <div class="panel p-3">
                  <h2 class="h5"><i class="fa-solid fa-clock-rotate-left me-2 icon-muted"></i>Recent memories</h2>
                  <div class="text-secondary small mb-2">{{ memory_total }} total · {{ per_page }} rows per page</div>
                  <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                      <thead><tr><th>ID</th><th>Agent</th><th>Workspace</th><th>Content</th><th></th></tr></thead>
                      <tbody>
                      {% for item in recent_memories %}
                        <tr class="clickable-row" data-memory-modal-target="memoryModal{{ item.id }}" title="Double-click to view full memory">
                          <td>{{ item.id }}</td>
                          <td>{{ item.agent_id }}</td>
                          <td>{{ item.workspace }}</td>
                          <td class="content-cell" title="{{ item.content }}">{{ item.content }}</td>
                          <td class="text-end">
                            <a class="btn btn-sm btn-outline-light" href="{{ url_for('edit_memory', memory_id=item.id, agent_id=item.agent_id, workspace=item.workspace) }}"><i class="fa-solid fa-pen-to-square me-1"></i>Edit</a>
                            <form class="d-inline" method="post" action="{{ url_for('delete_memory_admin', memory_id=item.id) }}" data-confirm="Delete this memory?">
                              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                              <input type="hidden" name="agent_id" value="{{ item.agent_id }}">
                              <input type="hidden" name="workspace" value="{{ item.workspace }}">
                              <button class="btn btn-sm btn-outline-danger"><i class="fa-solid fa-trash me-1"></i>Delete</button>
                            </form>
                          </td>
                        </tr>
                      {% else %}
                        <tr><td colspan="5" class="text-center text-secondary py-4">No memories yet.</td></tr>
                      {% endfor %}
                      </tbody>
                    </table>
                  </div>
                  {% for item in recent_memories %}
                  <div class="modal fade" id="memoryModal{{ item.id }}" tabindex="-1" aria-labelledby="memoryModal{{ item.id }}Title" aria-hidden="true">
                    <div class="modal-dialog modal-xl modal-dialog-scrollable">
                      <div class="modal-content panel">
                        <div class="modal-header">
                          <h5 class="modal-title" id="memoryModal{{ item.id }}Title"><i class="fa-solid fa-layer-group me-2 icon-muted"></i>Memory #{{ item.id }}</h5>
                          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                          <div class="row g-2 small text-secondary mb-3">
                            <div class="col-md-3"><span class="text-light">Agent:</span> {{ item.agent_id }}</div>
                            <div class="col-md-3"><span class="text-light">Workspace:</span> {{ item.workspace }}</div>
                            <div class="col-md-3"><span class="text-light">Type:</span> {{ item.memory_type }}</div>
                            <div class="col-md-3"><span class="text-light">Source:</span> {{ item.source }}</div>
                            <div class="col-md-3"><span class="text-light">Importance:</span> {{ item.importance }}</div>
                            <div class="col-md-3"><span class="text-light">Created:</span> {{ item.created_at }}</div>
                            <div class="col-md-3"><span class="text-light">Updated:</span> {{ item.updated_at }}</div>
                            <div class="col-md-3"><span class="text-light">Tags:</span> {{ item.tags|join(", ") }}</div>
                          </div>
                          <div class="memory-full-content p-3 rounded border bg-dark">{{ item.content }}</div>
                        </div>
                        <div class="modal-footer">
                          <a class="btn btn-outline-light" href="{{ url_for('edit_memory', memory_id=item.id, agent_id=item.agent_id, workspace=item.workspace) }}"><i class="fa-solid fa-pen-to-square me-1"></i>Edit</a>
                          <button type="button" class="btn btn-primary" data-bs-dismiss="modal">Close</button>
                        </div>
                      </div>
                    </div>
                  </div>
                  {% endfor %}
                  <nav class="mt-3">
                    <ul class="pagination mb-0">
                      <li class="page-item {% if memory_page <= 1 %}disabled{% endif %}"><a class="page-link" href="{{ ingest_page_url(memory_page=memory_page-1) }}">Previous</a></li>
                      <li class="page-item disabled"><span class="page-link">Page {{ memory_page }} of {{ memory_pages }}</span></li>
                      <li class="page-item {% if memory_page >= memory_pages %}disabled{% endif %}"><a class="page-link" href="{{ ingest_page_url(memory_page=memory_page+1) }}">Next</a></li>
                    </ul>
                  </nav>
                </div>
              </div>
              <div class="col-xl-5">
                <div class="panel p-3">
                  <h2 class="h5"><i class="fa-solid fa-file-lines me-2 icon-muted"></i>Recent documents</h2>
                  <div class="text-secondary small mb-2">{{ file_total }} total · {{ per_page }} rows per page</div>
                  <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                      <thead><tr><th>ID</th><th>File</th><th>Agent ID</th><th>Workspace</th><th></th></tr></thead>
                      <tbody>
                      {% for file in recent_files %}
                        <tr>
                          <td>{{ file.id }}</td>
                          <td class="content-cell" title="{{ file.original_filename }}">{{ file.original_filename }}</td>
                          <td>{{ file.agent_id }}</td>
                          <td>{{ file.workspace }}</td>
                          <td class="text-end">
                            <form method="post" action="{{ url_for('delete_file_admin', file_id=file.id) }}" data-confirm="Delete this document from future search?">
                              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                              <input type="hidden" name="agent_id" value="{{ file.agent_id }}">
                              <input type="hidden" name="workspace" value="{{ file.workspace }}">
                              <button class="btn btn-sm btn-outline-danger"><i class="fa-solid fa-trash me-1"></i>Delete</button>
                            </form>
                          </td>
                        </tr>
                      {% else %}
                        <tr><td colspan="5" class="text-center text-secondary py-4">No documents yet.</td></tr>
                      {% endfor %}
                      </tbody>
                    </table>
                  </div>
                  <nav class="mt-3">
                    <ul class="pagination mb-0">
                      <li class="page-item {% if file_page <= 1 %}disabled{% endif %}"><a class="page-link" href="{{ ingest_page_url(file_page=file_page-1) }}">Previous</a></li>
                      <li class="page-item disabled"><span class="page-link">Page {{ file_page }} of {{ file_pages }}</span></li>
                      <li class="page-item {% if file_page >= file_pages %}disabled{% endif %}"><a class="page-link" href="{{ ingest_page_url(file_page=file_page+1) }}">Next</a></li>
                    </ul>
                  </nav>
                </div>
              </div>
            </div>
            """,
            scopes=scopes,
            recent_memories=[row_to_memory(row) for row in recent_memories],
            recent_files=recent_files,
            per_page=per_page,
            scope_page=scope_page,
            scope_pages=scope_pages,
            scope_total=scope_total,
            memory_page=memory_page,
            memory_pages=memory_pages,
            memory_total=memory_total,
            file_page=file_page,
            file_pages=file_pages,
            file_total=file_total,
            ingest_page_url=lambda **updates: url_for(
                "ingest",
                per_page=updates.get("per_page", per_page),
                scope_page=updates.get("scope_page", scope_page),
                memory_page=updates.get("memory_page", memory_page),
                file_page=updates.get("file_page", file_page),
            ),
        )

    @app.route("/memories")
    @login_required
    def memories():
        page = max(1, int(request.args.get("page", "1") or "1"))
        per_page = per_page_param()
        agent_id = request.args.get("agent_id") or None
        workspace = request.args.get("workspace") or None
        query = request.args.get("q") or None
        rows, total = db.list_memories(agent_id, workspace, query, per_page, (page - 1) * per_page)
        items = [row_to_memory(row) for row in rows]
        pages = max(1, math.ceil(total / per_page))
        return render(
            "Memories",
            """
            <div class="d-flex align-items-center justify-content-between mb-3">
              <h1 class="h3 mb-0"><i class="fa-solid fa-layer-group me-2 icon-muted"></i>Memories</h1>
              <span class="badge text-bg-secondary">{{ total }} total</span>
            </div>
            <form class="panel p-3 mb-3" method="get">
              <div class="row g-2">
                <div class="col-md-3"><input class="form-control" name="agent_id" placeholder="Agent" value="{{ agent_id or '' }}"></div>
                <div class="col-md-3"><input class="form-control" name="workspace" placeholder="Workspace" value="{{ workspace or '' }}"></div>
                <div class="col-md-4"><input class="form-control" name="q" placeholder="Search content, tags, source" value="{{ query or '' }}"></div>
                <div class="col-md-2 d-grid"><button class="btn btn-primary"><i class="fa-solid fa-filter me-1"></i>Filter</button></div>
              </div>
            </form>
            <div class="panel p-3">
              <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                  <thead><tr><th>ID</th><th>Agent</th><th>Workspace</th><th>Type</th><th>Source</th><th>Content</th><th>Updated</th><th></th></tr></thead>
                  <tbody>
                  {% for item in items %}
                    <tr class="clickable-row" data-memory-modal-target="memoryModal{{ item.id }}" title="Double-click to view full memory">
                      <td>{{ item.id }}</td>
                      <td>{{ item.agent_id }}</td>
                      <td>{{ item.workspace }}</td>
                      <td><span class="badge text-bg-info">{{ item.memory_type }}</span></td>
                      <td>{{ item.source }}</td>
                      <td class="content-cell" title="{{ item.content }}">{{ item.content }}</td>
                      <td>{{ item.updated_at }}</td>
                      <td class="text-end">
                        <a class="btn btn-sm btn-outline-light" href="{{ url_for('edit_memory', memory_id=item.id, agent_id=item.agent_id, workspace=item.workspace) }}"><i class="fa-solid fa-pen-to-square me-1"></i>Edit</a>
                        <form class="d-inline" method="post" action="{{ url_for('delete_memory_admin', memory_id=item.id) }}" data-confirm="Delete this memory?">
                          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                          <input type="hidden" name="agent_id" value="{{ item.agent_id }}">
                          <input type="hidden" name="workspace" value="{{ item.workspace }}">
                          <button class="btn btn-sm btn-outline-danger"><i class="fa-solid fa-trash me-1"></i>Delete</button>
                        </form>
                      </td>
                    </tr>
                  {% else %}
                    <tr><td colspan="8" class="text-center text-secondary py-4">No memories match this filter.</td></tr>
                  {% endfor %}
                  </tbody>
                </table>
              </div>
              {% for item in items %}
              <div class="modal fade" id="memoryModal{{ item.id }}" tabindex="-1" aria-labelledby="memoryModal{{ item.id }}Title" aria-hidden="true">
                <div class="modal-dialog modal-xl modal-dialog-scrollable">
                  <div class="modal-content panel">
                    <div class="modal-header">
                      <h5 class="modal-title" id="memoryModal{{ item.id }}Title"><i class="fa-solid fa-layer-group me-2 icon-muted"></i>Memory #{{ item.id }}</h5>
                      <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                      <div class="row g-2 small text-secondary mb-3">
                        <div class="col-md-3"><span class="text-light">Agent:</span> {{ item.agent_id }}</div>
                        <div class="col-md-3"><span class="text-light">Workspace:</span> {{ item.workspace }}</div>
                        <div class="col-md-3"><span class="text-light">Type:</span> {{ item.memory_type }}</div>
                        <div class="col-md-3"><span class="text-light">Source:</span> {{ item.source }}</div>
                        <div class="col-md-3"><span class="text-light">Importance:</span> {{ item.importance }}</div>
                        <div class="col-md-3"><span class="text-light">Created:</span> {{ item.created_at }}</div>
                        <div class="col-md-3"><span class="text-light">Updated:</span> {{ item.updated_at }}</div>
                        <div class="col-md-3"><span class="text-light">Tags:</span> {{ item.tags|join(", ") }}</div>
                      </div>
                      <div class="memory-full-content p-3 rounded border bg-dark">{{ item.content }}</div>
                    </div>
                    <div class="modal-footer">
                      <a class="btn btn-outline-light" href="{{ url_for('edit_memory', memory_id=item.id, agent_id=item.agent_id, workspace=item.workspace) }}"><i class="fa-solid fa-pen-to-square me-1"></i>Edit</a>
                      <button type="button" class="btn btn-primary" data-bs-dismiss="modal">Close</button>
                    </div>
                  </div>
                </div>
              </div>
              {% endfor %}
              <nav class="mt-3">
                <ul class="pagination mb-0">
                  <li class="page-item {% if page <= 1 %}disabled{% endif %}"><a class="page-link" href="{{ page_url(page-1) }}">Previous</a></li>
                  <li class="page-item disabled"><span class="page-link">Page {{ page }} of {{ pages }} · {{ per_page }} rows</span></li>
                  <li class="page-item {% if page >= pages %}disabled{% endif %}"><a class="page-link" href="{{ page_url(page+1) }}">Next</a></li>
                </ul>
              </nav>
            </div>
            """,
            items=items,
            total=total,
            page=page,
            pages=pages,
            per_page=per_page,
            agent_id=agent_id,
            workspace=workspace,
            query=query,
            page_url=lambda p: url_for("memories", page=max(1, p), per_page=per_page, agent_id=agent_id or "", workspace=workspace or "", q=query or ""),
        )

    @app.route("/memories/<int:memory_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_memory(memory_id: int):
        agent_id = clean_form_text(request.values.get("agent_id"), 128)
        workspace = clean_form_text(request.values.get("workspace"), 256)
        if not agent_id or not workspace:
            flash("Agent and workspace are required.", "danger")
            return redirect(url_for("memories"))
        if request.method == "POST":
            if not validate_csrf():
                flash("Invalid session token.", "danger")
            else:
                try:
                    memory_service.update_memory(
                        MemoryUpdateRequest(
                            id=memory_id,
                            agent_id=agent_id,
                            workspace=workspace,
                            source=clean_form_text(request.form.get("source"), 256),
                            memory_type=clean_form_text(request.form.get("memory_type"), 64),
                            content=(request.form.get("content") or "").strip(),
                            tags=parse_tags(clean_form_text(request.form.get("tags"), 1024)),
                            importance=float(request.form.get("importance") or "0.5"),
                        )
                    )
                    flash("Memory updated.", "success")
                    return redirect(url_for("memories", agent_id=agent_id, workspace=workspace))
                except Exception as exc:
                    flash(f"Update failed: {escape(str(exc))}", "danger")
        try:
            item = memory_service.get_memory(memory_id, agent_id, workspace)
        except Exception as exc:
            flash(f"Memory not found: {escape(str(exc))}", "danger")
            return redirect(url_for("memories"))
        return render(
            "Edit Memory",
            """
            <div class="d-flex align-items-center justify-content-between mb-3">
              <h1 class="h3 mb-0"><i class="fa-solid fa-pen-to-square me-2 icon-muted"></i>Edit Memory</h1>
              <a class="btn btn-outline-light" href="{{ url_for('memories', agent_id=item.agent_id, workspace=item.workspace) }}"><i class="fa-solid fa-arrow-left me-1"></i>Back</a>
            </div>
            <form class="panel p-3" method="post">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <input type="hidden" name="agent_id" value="{{ item.agent_id }}">
              <input type="hidden" name="workspace" value="{{ item.workspace }}">
              <div class="row g-3">
                <div class="col-md-4"><label class="form-label">Agent</label><input class="form-control" value="{{ item.agent_id }}" disabled></div>
                <div class="col-md-4"><label class="form-label">Workspace</label><input class="form-control" value="{{ item.workspace }}" disabled></div>
                <div class="col-md-4"><label class="form-label">Importance</label><input class="form-control" name="importance" type="number" min="0" max="1" step="0.1" value="{{ item.importance }}"></div>
                <div class="col-md-4"><label class="form-label">Source</label><input class="form-control" name="source" value="{{ item.source }}" required></div>
                <div class="col-md-4"><label class="form-label">Memory type</label><input class="form-control" name="memory_type" value="{{ item.memory_type }}" required></div>
                <div class="col-md-4"><label class="form-label">Tags</label><input class="form-control" name="tags" value="{{ tags }}"></div>
                <div class="col-12"><label class="form-label">Content</label><textarea class="form-control sql-editor" name="content" required>{{ item.content }}</textarea></div>
              </div>
              <div class="d-flex justify-content-between mt-3">
                <button class="btn btn-primary"><i class="fa-solid fa-floppy-disk me-1"></i>Save changes</button>
              </div>
            </form>
            """,
            item=item,
            tags=", ".join(item["tags"]),
        )

    @app.route("/memories/<int:memory_id>/delete", methods=["POST"])
    @login_required
    def delete_memory_admin(memory_id: int):
        if not validate_csrf():
            flash("Invalid session token.", "danger")
            return redirect(url_for("memories"))
        agent_id = clean_form_text(request.form.get("agent_id"), 128)
        workspace = clean_form_text(request.form.get("workspace"), 256)
        try:
            memory_service.delete_memory(MemoryDeleteRequest(id=memory_id, agent_id=agent_id, workspace=workspace))
            flash("Memory deleted.", "success")
        except Exception as exc:
            flash(f"Delete failed: {escape(str(exc))}", "danger")
        return redirect(request.referrer or url_for("memories", agent_id=agent_id, workspace=workspace))

    @app.route("/files/<int:file_id>/delete", methods=["POST"])
    @login_required
    def delete_file_admin(file_id: int):
        if not validate_csrf():
            flash("Invalid session token.", "danger")
            return redirect(url_for("ingest"))
        agent_id = clean_form_text(request.form.get("agent_id"), 128)
        workspace = clean_form_text(request.form.get("workspace"), 256)
        try:
            file_service.delete_file(file_id, agent_id, workspace)
            flash("Document deleted from future search.", "success")
        except Exception as exc:
            flash(f"Document delete failed: {escape(str(exc))}", "danger")
        return redirect(request.referrer or url_for("ingest"))

    @app.route("/api-keys", methods=["GET", "POST"])
    @login_required
    def api_keys():
        created_key = None
        page = page_param()
        per_page = per_page_param()
        if request.method == "POST":
            if not validate_csrf():
                flash("Invalid session token.", "danger")
            else:
                name = clean_form_text(request.form.get("name"), 128)
                role = request.form.get("role") or "agent"
                agent_id = clean_form_text(request.form.get("agent_id"), 128) or None
                workspace = clean_form_text(request.form.get("workspace"), 256) or None
                if not name:
                    flash("Name is required.", "danger")
                elif role not in {"admin", "agent"}:
                    flash("Invalid role.", "danger")
                elif role == "agent" and (not agent_id or not workspace):
                    flash("Agent keys require both agent and workspace.", "danger")
                else:
                    created_key = generate_api_key()
                    db.create_api_key(name, hash_api_key(created_key), key_prefix(created_key), created_key, role, agent_id if role == "agent" else None, workspace if role == "agent" else None)
                    flash("API key created.", "success")
        all_keys = [dict(row) for row in db.list_api_keys()]
        keys, total, pages = paginate_list(all_keys, page, per_page)
        return render(
            "API Keys",
            """
            <div class="row g-3">
              <div class="col-lg-4">
                <div class="panel p-3">
                  <h1 class="h4"><i class="fa-solid fa-key me-2 icon-muted"></i>Create API Key</h1>
                  <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <div class="mb-2"><label class="form-label"><i class="fa-solid fa-tag me-1"></i>Name</label><input class="form-control" name="name" required></div>
                    <div class="mb-2">
                      <label class="form-label"><i class="fa-solid fa-user-gear me-1"></i>Role</label>
                      <select class="form-select" name="role"><option value="agent">Agent scoped</option><option value="admin">Admin</option></select>
                    </div>
                    <div class="mb-2"><label class="form-label"><i class="fa-solid fa-robot me-1"></i>Agent</label><input class="form-control" name="agent_id"></div>
                    <div class="mb-3"><label class="form-label"><i class="fa-solid fa-folder-tree me-1"></i>Workspace</label><input class="form-control" name="workspace"></div>
                    <button class="btn btn-primary w-100"><i class="fa-solid fa-plus me-1"></i>Create</button>
                  </form>
                </div>
              </div>
              <div class="col-lg-8">
                <div class="panel p-3">
                  <h2 class="h4"><i class="fa-solid fa-list-check me-2 icon-muted"></i>Keys</h2>
                  <div class="text-secondary small mb-2">{{ total }} total · {{ per_page }} rows per page</div>
                  <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                      <thead><tr><th>Name</th><th>Key</th><th>Role</th><th>Scope</th><th>Status</th><th>Last Used</th><th></th></tr></thead>
                      <tbody>
                      {% for key in keys %}
                        <tr>
                          <td>{{ key.name }}</td>
                          <td>
                            <div class="d-flex align-items-center gap-2">
                              <span class="secret-box">{{ key.key_prefix }}...</span>
                              {% if key.key_secret %}
                              <button type="button" class="btn btn-sm btn-outline-light" data-copy-secret="{{ key.key_secret }}"><i class="fa-solid fa-copy me-1"></i>Copy</button>
                              {% else %}
                              <span class="badge text-bg-secondary">prefix only</span>
                              {% endif %}
                            </div>
                          </td>
                          <td>{{ key.role }}</td>
                          <td>{{ key.agent_id or '*' }} / {{ key.workspace or '*' }}</td>
                          <td>{% if key.active %}<span class="badge text-bg-success">active</span>{% else %}<span class="badge text-bg-secondary">revoked</span>{% endif %}</td>
                          <td>{{ key.last_used_at or '' }}</td>
                          <td class="text-end">
                            {% if key.active %}
                            <form method="post" action="{{ url_for('revoke_key', key_id=key.id) }}">
                              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                              <button class="btn btn-sm btn-outline-danger"><i class="fa-solid fa-ban me-1"></i>Revoke</button>
                            </form>
                            {% else %}
                            <form method="post" action="{{ url_for('delete_key', key_id=key.id) }}" data-confirm="Permanently delete this revoked API key record?">
                              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                              <button class="btn btn-sm btn-outline-danger"><i class="fa-solid fa-trash me-1"></i>Delete</button>
                            </form>
                            {% endif %}
                          </td>
                        </tr>
                      {% else %}
                        <tr><td colspan="7" class="text-center text-secondary py-4">No database-backed API keys yet.</td></tr>
                      {% endfor %}
                      </tbody>
                    </table>
                  </div>
                  <nav class="mt-3">
                    <ul class="pagination mb-0">
                      <li class="page-item {% if page <= 1 %}disabled{% endif %}"><a class="page-link" href="{{ page_url(page-1) }}">Previous</a></li>
                      <li class="page-item disabled"><span class="page-link">Page {{ page }} of {{ pages }}</span></li>
                      <li class="page-item {% if page >= pages %}disabled{% endif %}"><a class="page-link" href="{{ page_url(page+1) }}">Next</a></li>
                    </ul>
                  </nav>
                </div>
              </div>
            </div>
            """,
            keys=keys,
            created_key=created_key,
            total=total,
            page=page,
            pages=pages,
            per_page=per_page,
            page_url=lambda p: url_for("api_keys", page=max(1, p), per_page=per_page),
        )

    @app.route("/api-keys/<int:key_id>/revoke", methods=["POST"])
    @login_required
    def revoke_key(key_id: int):
        if not validate_csrf():
            flash("Invalid session token.", "danger")
        elif db.revoke_api_key(key_id):
            flash("API key revoked.", "success")
        else:
            flash("API key was already inactive or missing.", "warning")
        return redirect(url_for("api_keys"))

    @app.route("/api-keys/<int:key_id>/delete", methods=["POST"])
    @login_required
    def delete_key(key_id: int):
        if not validate_csrf():
            flash("Invalid session token.", "danger")
        elif db.delete_inactive_api_key(key_id):
            flash("Revoked API key deleted.", "success")
        else:
            flash("Only revoked API keys can be deleted.", "warning")
        return redirect(url_for("api_keys"))

    return app
