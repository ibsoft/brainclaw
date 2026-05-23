<img width="1536" height="1024" alt="ChatGPT Image May 20, 2026, 02_40_52 PM" src="https://github.com/user-attachments/assets/5a0d99c8-cfae-4e4e-9420-5a82d62b0d77" />
<img width="1910" height="993" alt="image" src="https://github.com/user-attachments/assets/876865e8-f6c0-4bda-886c-b031009db7b5" />
<img width="1915" height="989" alt="image" src="https://github.com/user-attachments/assets/50f35fb0-b5ab-42ff-8d31-175e953ce6bd" />
<img width="1917" height="983" alt="image" src="https://github.com/user-attachments/assets/802303cb-8007-478d-ade4-d094616f584e" />


# BrainClaw

BrainClaw is a local long-term semantic memory service for OpenClaw. It uses FastAPI for the HTTP API, SQLite for durable memory metadata, FAISS for local vector search, and sentence-transformers for local embeddings.

The service binds to `127.0.0.1` by default. Keep it local unless you add TLS, firewalling, and stronger authentication.

## Install

Use Python 3.11 or 3.12 for the most reliable FAISS, PyTorch, and sentence-transformers wheel support. Python 3.14 may not have compatible wheels for the full local embedding stack yet.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `MEMORY_API_KEY` to a long random value.

BrainClaw defaults to a multilingual embedding model:

```text
EMBEDDING_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DIMENSION=384
```

Use a multilingual model if you store or query Greek or other non-English text. If you change `EMBEDDING_MODEL_NAME`, rebuild the FAISS indexes because old vectors were created with the previous model.

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Run

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8757
```

Admin UI:

```text
http://127.0.0.1:8757/admin
```

Set `ADMIN_SESSION_SECRET` in `.env` before using the admin UI. On first visit, BrainClaw redirects to `/admin/setup` so you can create the admin username and password. The password is stored only as a hash in SQLite.

Admin usernames must be 3-64 characters and may contain letters, numbers, `.`, `_`, `-`, and `@`. Admin passwords must be at least 12 characters and include uppercase, lowercase, number, and symbol characters.

Admin tables are paginated. The default page size is 50 rows; most table URLs accept `page` and `per_page` query parameters.

The top menu includes `Backup` for exporting, restoring, or purging BrainClaw data. `Create backup` saves a zip under `data/backups`, and the saved backups table lets you download or delete each zip from disk. A backup zip contains the SQLite database, FAISS indexes, ID maps, and uploaded document storage so the same memories can be restored on another system. Existing server-side backup zips are not included inside new backups and are preserved during restore/purge.

Double-click a memory table row in the admin UI to open the full formatted memory content in a modal.

Health check:

```bash
curl -H "X-API-Key: $MEMORY_API_KEY" \
  http://127.0.0.1:8757/health
```

## Linux systemd Service

The repo includes `brainclaw.service` for a local Linux install under `/opt/brainclaw`.

Quick install from the repo checkout:

```bash
sudo ./scripts/install-linux-service.sh
```

Quick uninstall, keeping installed files and memory data:

```bash
sudo ./scripts/uninstall-linux-service.sh
```

Uninstall and remove `/opt/brainclaw`:

```bash
sudo REMOVE_DATA=true ./scripts/uninstall-linux-service.sh
```

Remove the service user too:

```bash
sudo REMOVE_DATA=true REMOVE_USER=true ./scripts/uninstall-linux-service.sh
```

Installer defaults:

- `SERVICE_NAME=brainclaw`
- `SERVICE_USER=brainclaw`
- `INSTALL_DIR=/opt/brainclaw`
- `PYTHON_BIN=python3.12`

Override example:

```bash
sudo INSTALL_DIR=/srv/brainclaw PYTHON_BIN=python3.11 ./scripts/install-linux-service.sh
```

Manual install steps, equivalent to what the script automates:

```bash
sudo useradd --system --home /opt/brainclaw --shell /usr/sbin/nologin brainclaw
sudo mkdir -p /opt/brainclaw
sudo rsync -a --exclude .git ./ /opt/brainclaw/
sudo chown -R brainclaw:brainclaw /opt/brainclaw
cd /opt/brainclaw
sudo -u brainclaw python3.12 -m venv .venv
sudo -u brainclaw .venv/bin/pip install -r requirements.txt
sudo -u brainclaw cp .env.example .env
sudo -u brainclaw python3 - <<'PY'
import secrets
from pathlib import Path

env = Path(".env")
text = env.read_text()
text = text.replace("replace-with-a-long-random-local-key", secrets.token_urlsafe(32))
text = text.replace("replace-with-a-long-random-session-secret", secrets.token_urlsafe(32))
env.write_text(text)
PY
sudo cp brainclaw.service /etc/systemd/system/brainclaw.service
sudo systemctl daemon-reload
sudo systemctl enable --now brainclaw
```

Check it:

```bash
sudo systemctl status brainclaw
sudo journalctl -u brainclaw -f
curl -H "X-API-Key: $(sudo sed -n 's/^MEMORY_API_KEY=//p' /opt/brainclaw/.env)" \
  http://127.0.0.1:8757/health
```

The unit runs as the `brainclaw` system user, binds to `127.0.0.1`, applies systemd hardening, and only grants write access to `/opt/brainclaw/data`.

## All-in-One OpenClaw + BrainClaw Setup

`setup.sh` is an interactive Linux bootstrap script. It installs OS dependencies, creates an `openclaw` Linux user, asks you to set that user's password, installs OpenClaw under that user's home directory, installs BrainClaw from this checkout as a systemd service, installs the OpenClaw prompt/default files, and attempts to enable the OpenClaw gateway service.

Supported targets:

- Linux with systemd and one of: `apt-get`, `dnf`, `yum`, `pacman`, `zypper`, or `apk`
- WSL distributions with systemd enabled

WSL requirement: systemd must be enabled. In WSL, check:

```bash
ps -p 1 -o comm=
```

It should print `systemd`. If not, create or edit `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

Then restart WSL from Windows PowerShell:

```powershell
wsl --shutdown
```

Run the all-in-one installer:

```bash
git clone https://github.com/ibsoft/brainclaw.git
cd brainclaw
sudo ./setup.sh install
```

The script will prompt:

```text
Continue? [y/N]
Choose bind address [1]:
Set Linux password for openclaw:
Confirm password:
```

Bind choices are localhost only (`127.0.0.1`), all interfaces (`0.0.0.0`), or a custom IP address. For non-interactive installs, set `BRAINCLAW_HOST=127.0.0.1`, `BRAINCLAW_HOST=0.0.0.0`, or `BRAINCLAW_HOST=<ip-address>`.

The installer writes the selected BrainClaw URL into `/etc/openclaw/environment.conf` and renders the installed OpenClaw instruction files with that URL, so OpenClaw knows where the BrainClaw API lives.

Every `setup.sh install` resets the installed BrainClaw SQLite database, FAISS indexes, and uploads to defaults while preserving saved backup zips. To generate HTTPS URLs and run Uvicorn with TLS, set `BRAINCLAW_SCHEME=https`, `BRAINCLAW_SSL_CERTFILE=/path/cert.pem`, and `BRAINCLAW_SSL_KEYFILE=/path/key.pem`.

BrainClaw writes JSONL logs with rotation to `data/logs/brainclaw.jsonl` by default. Configure rotation with `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT`; view and search logs from the admin `Logs` menu.

To re-inject BrainClaw into an existing OpenClaw user without reinstalling BrainClaw, run:

```bash
sudo ./setup.sh inject-openclaw
```

This updates `/etc/openclaw/environment.conf`, installs rendered OpenClaw instruction files, copies the BrainClaw environment into the OpenClaw user profile, and adds `openclaw-with-brainclaw` / `openclaw-memory` launch helpers.

Default paths:

```text
OpenClaw user:       openclaw
OpenClaw install:    /home/openclaw/openclaw
OpenClaw npm prefix: /home/openclaw/openclaw/npm
OpenClaw workspace:  /home/openclaw/workspace
BrainClaw install:   /opt/brainclaw
BrainClaw service:   brainclaw
BrainClaw bind:      127.0.0.1
BrainClaw admin:     http://127.0.0.1:8757/admin
```

Override example:

```bash
sudo OPENCLAW_USER=myopenclaw \
  OPENCLAW_AGENT_ID=Kim \
  OPENCLAW_WORKSPACE=Kims-workspace \
  BRAINCLAW_DIR=/opt/brainclaw \
  ./setup.sh install
```

Uninstall the service:

```bash
sudo ./setup.sh uninstall
sudo REMOVE_DATA=1 REMOVE_OPENCLAW=1 REMOVE_OPENCLAW_USER=1 ./setup.sh uninstall
```

Post-install checks:

```bash
sudo systemctl status brainclaw
curl -H "X-API-Key: $(sudo sed -n 's/^MEMORY_API_KEY=//p' /opt/brainclaw/.env)" \
  http://127.0.0.1:8757/health
sudo -iu openclaw /home/openclaw/openclaw/npm/bin/openclaw gateway status
```

Start OpenClaw with BrainClaw environment loaded:

```bash
sudo -iu openclaw
openclaw-brainclaw /home/openclaw/openclaw/npm/bin/openclaw
```

Then open:

```text
http://127.0.0.1:8757/admin
```

Complete the BrainClaw first-run admin setup in the browser.

Notes:

- The script currently targets apt-based Linux systems.
- OpenClaw is installed with npm under `/home/openclaw/openclaw/npm`, not into a system-global npm prefix.
- BrainClaw runs as its own `brainclaw` service user by default.
- On WSL, services only run while the WSL distro is running.

## API

All endpoints require:

```text
X-API-Key: your-memory-api-key
```

For manual testing, export the key:

```bash
export MEMORY_API_KEY="$(sed -n 's/^MEMORY_API_KEY=//p' .env)"
export BRAINCLAW_URL="http://127.0.0.1:8757"
```

### Add Memory

```bash
curl -X POST http://127.0.0.1:8757/memory/add \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "agent_id": "openclaw",
    "workspace": "default",
    "source": "chat",
    "memory_type": "preference",
    "content": "The user prefers concise implementation summaries with exact file references.",
    "tags": ["user-preference", "communication"],
    "importance": 0.8
  }'
```

### Search Memory

```bash
curl -X POST http://127.0.0.1:8757/memory/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "agent_id": "openclaw",
    "workspace": "default",
    "query": "How should I summarize code changes for this user?",
    "top_k": 5,
    "min_score": 0.25,
    "tags": ["user-preference"]
  }'
```

### Get Memory

```bash
curl -H "X-API-Key: $MEMORY_API_KEY" \
  "http://127.0.0.1:8757/memory/1?agent_id=openclaw&workspace=default"
```

### Update Memory

```bash
curl -X POST http://127.0.0.1:8757/memory/update \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "id": 1,
    "agent_id": "openclaw",
    "workspace": "default",
    "content": "The user prefers concise summaries with exact file references and verification notes.",
    "importance": 0.9
  }'
```

### Delete Memory

```bash
curl -X POST http://127.0.0.1:8757/memory/delete \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "id": 1,
    "agent_id": "openclaw",
    "workspace": "default"
  }'
```

### Rebuild FAISS Index

```bash
curl -X POST http://127.0.0.1:8757/memory/rebuild-index \
  -H "X-API-Key: $MEMORY_API_KEY"
```

Rebuild after changing embedding models or after enabling isolated indexes.

### Manual curl Test Flow

Create a memory:

```bash
curl -sS -X POST "$BRAINCLAW_URL/memory/add" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "agent_id": "curl-agent",
    "workspace": "default",
    "source": "manual-curl",
    "memory_type": "note",
    "content": "BrainClaw manual curl test memory about secure local operations.",
    "tags": ["manual", "curl"],
    "importance": 0.7
  }'
```

Search it:

```bash
curl -sS -X POST "$BRAINCLAW_URL/memory/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "agent_id": "curl-agent",
    "workspace": "default",
    "query": "secure local operations",
    "top_k": 5,
    "min_score": 0.1
  }'
```

Upload a document:

```bash
printf 'BrainClaw curl upload test document.\n' > /tmp/brainclaw-upload-test.txt
curl -sS -X POST "$BRAINCLAW_URL/files/upload" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -F "agent_id=curl-agent" \
  -F "workspace=default" \
  -F "source=manual-upload" \
  -F "tags=[\"manual\",\"upload\"]" \
  -F "file=@/tmp/brainclaw-upload-test.txt"
```

Search uploaded documents:

```bash
curl -sS -X POST "$BRAINCLAW_URL/files/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "agent_id": "curl-agent",
    "workspace": "default",
    "query": "upload test document",
    "top_k": 5,
    "min_score": 0.1
  }'
```

Update a memory after noting its returned `id`:

```bash
curl -sS -X POST "$BRAINCLAW_URL/memory/update" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "id": 1,
    "agent_id": "curl-agent",
    "workspace": "default",
    "content": "Updated BrainClaw manual curl test memory.",
    "tags": ["manual", "curl", "updated"],
    "importance": 0.8
  }'
```

Delete a memory:

```bash
curl -sS -X POST "$BRAINCLAW_URL/memory/delete" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "id": 1,
    "agent_id": "curl-agent",
    "workspace": "default"
  }'
```

## Storage

Runtime files are created under `data/`:

- `data/memory.sqlite3` stores raw memory records and chunk metadata.
- `data/faiss.index` stores the FAISS vector index.
- `data/id_map.json` maps FAISS positions back to SQLite chunk and memory IDs.
- `data/indexes/` stores isolated FAISS indexes when `ISOLATE_INDEXES=true`.
- `data/uploads/` stores uploaded files with safe UUID filenames.

Long content is split into overlapping chunks. Every chunk is embedded, normalized, and stored in FAISS using `IndexFlatIP`, which provides cosine similarity for normalized vectors.

## Isolation

`ISOLATE_INDEXES=true` is the default. In that mode BrainClaw keeps a separate FAISS index and ID map for each `agent_id` + `workspace`, so vector search never probes another agent/workspace and filters afterward.

The legacy `MEMORY_API_KEY` is treated as an admin key. Additional API keys can be created in `/admin/api-keys`; agent keys are bound to one `agent_id` + `workspace` and receive `403` if they try to read, search, write, update, delete, upload, or reindex another scope.

If you already have memories from an older global-index setup, rebuild once after enabling isolation:

```bash
curl -X POST http://127.0.0.1:8757/memory/rebuild-index \
  -H "X-API-Key: $MEMORY_API_KEY"
```

This creates the per-scope indexes under `data/indexes/`.

## Admin SQL Query

The admin UI includes a read-only SQL query screen at:

```text
http://127.0.0.1:8757/admin/query
```

BrainClaw accepts a deliberately small query language, called BrainQL, that is just a constrained SQLite subset:

- One statement only.
- Statement must start with `SELECT` or `WITH`.
- Mutating and operational statements such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `PRAGMA`, `ATTACH`, `DETACH`, and `VACUUM` are blocked.
- Internal credential storage such as `app_settings`, `key_hash`, and `password_hash` is blocked.
- The admin UI displays at most 200 rows.

Useful tables:

- `memories`: memory records, including `agent_id`, `workspace`, `source`, `memory_type`, `content`, `tags_json`, `importance`, timestamps, and `deleted`.
- `chunks`: memory chunks with `memory_id`, `chunk_index`, and `text`.
- `files`: uploaded file records.
- `file_chunks`: indexed uploaded-file chunks.
- `api_keys`: API key metadata. Secret hashes are not exposed through BrainQL.

Examples:

```sql
SELECT agent_id, workspace, COUNT(*) AS memories
FROM memories
WHERE deleted = 0
GROUP BY agent_id, workspace;
```

```sql
SELECT m.id, m.agent_id, m.workspace, c.text
FROM chunks c
JOIN memories m ON m.id = c.memory_id
WHERE m.deleted = 0 AND c.deleted = 0
  AND c.text LIKE '%security%'
LIMIT 50;
```

## Admin Ingest

The admin UI can add notes or upload documents from:

```text
http://127.0.0.1:8757/admin/ingest
```

Ingest modes:

- `Note to memory`: stores the text as a normal memory record and indexes its chunks.
- `Document upload`: stores the uploaded file, extracts text, chunks it, and indexes the chunks.

Targets:

- `One agent/workspace`: provide `agent_id` and `workspace`. This can create a new scope.
- `All existing agents/workspaces`: copies the same note or document into every current scope listed in the admin UI.

Document uploads use the same security checks as the API upload path: size limits, allowed extensions, secret-pattern rejection, safe filenames, local storage under `data/uploads/`, and per-scope FAISS indexes.

The ingest screen also shows recent memories and documents:

- Memories can be edited or deleted from the admin UI.
- Documents can be deleted from future search results. To replace a document, delete it and upload the replacement.
- Upload/ingest forms show a spinner and disable submit buttons while embedding and indexing are running.

## OpenClaw Prompt Persistence

`OpenClaw.md` is intended to be installed as OpenClaw's persistent system prompt or startup instruction file. Pasting it into a normal chat is not enough if `/new` clears chat context.

Install the prompt and a starter environment file:

```bash
sudo ./scripts/install-openclaw-prompt.sh
```

The installer deploys:

- `/etc/openclaw/OpenClaw.md`
- `/etc/openclaw/defaults/AGENTS.md`
- `/etc/openclaw/defaults/BOOTSTRAP.md`
- `/etc/openclaw/defaults/HEARTBEAT.md`
- `/etc/openclaw/defaults/IDENTITY.md`
- `/etc/openclaw/defaults/MEMORY.md`
- `/etc/openclaw/defaults/SOUL.md`
- `/etc/openclaw/defaults/TOOLS.md`
- `/etc/openclaw/defaults/USER.md`

It also injects the same files into the OpenClaw workspace. By default the workspace target is the current repo directory. To inject another workspace:

```bash
sudo OPENCLAW_WORKSPACE_DIR=/path/to/openclaw/workspace \
  ./scripts/install-openclaw-prompt.sh
```

Then edit:

```bash
sudo nano /etc/openclaw/environment.conf
```

Set:

```bash
BRAINCLAW_URL=http://127.0.0.1:8757
BRAINCLAW_API_KEY=your-brainclaw-api-key
OPENCLAW_AGENT_ID=BrainClaw
OPENCLAW_WORKSPACE=BrainClaws-workspace
OPENCLAW_SYSTEM_PROMPT=/etc/openclaw/OpenClaw.md
OPENCLAW_DEFAULTS_DIR=/etc/openclaw/defaults
OPENCLAW_WORKSPACE_DIR=/path/to/openclaw/workspace
```

OpenClaw itself must be configured to load `/etc/openclaw/OpenClaw.md` as a system prompt on every session, including after `/new`. If OpenClaw does not reload that file after `/new`, it will forget the BrainClaw rules and may fall back to its own local memory mechanism.

The installer also creates a generic wrapper:

```bash
/usr/local/bin/openclaw-brainclaw
```

Use it to start your OpenClaw command with BrainClaw variables loaded:

```bash
openclaw-brainclaw <your-openclaw-command> [args...]
```

The wrapper exports:

- `BRAINCLAW_URL`
- `BRAINCLAW_API_KEY`
- `OPENCLAW_AGENT_ID`
- `OPENCLAW_WORKSPACE`
- `OPENCLAW_SYSTEM_PROMPT`
- `OPENCLAW_PROMPT_FILE`
- `OPENCLAW_INSTRUCTIONS_FILE`
- `SYSTEM_PROMPT_FILE`

OpenClaw must consume one of the prompt file variables or be configured separately to load `/etc/openclaw/OpenClaw.md`. The wrapper cannot force prompt loading if OpenClaw ignores all prompt-file environment variables.

## Security Notes

- Full memory content is not logged by default.
- Obvious API keys, private keys, passwords, tokens, and SSH keys are rejected.
- Log previews are redacted and truncated.
- Input sizes, upload size, tag counts, content length, query length, and `top_k` are bounded.
- Configured file paths must remain inside the project directory.
- `MEMORY_API_KEY` is required for memory endpoints unless `ALLOW_MISSING_API_KEY=true` is explicitly set.
- Agent API keys are stored as SHA-256 hashes and shown only once at creation.
- Admin browser forms use a first-run setup screen, hashed passwords, login sessions, CSRF tokens, `HttpOnly`/`SameSite=Strict` cookies, and defensive response headers.
- Admin SQL querying is read-only, single-statement, and blocks credential internals.
- Uploaded files are never executed, are stored outside any public web directory, and only approved extensions are accepted.

This is local memory infrastructure, not a public internet service.

## File Upload And Search

Supported upload extensions:

```text
.txt .md .pdf .docx .csv .json .log .py .cs .js .yaml .yml .conf .service .html
```

Upload and index a file:

```bash
curl -X POST http://127.0.0.1:8757/files/upload \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -F "agent_id=openclaw" \
  -F "workspace=default" \
  -F "source=repo-docs" \
  -F 'tags=["docs","project"]' \
  -F "file=@README.md"
```

Search uploaded files:

```bash
curl -X POST http://127.0.0.1:8757/files/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $MEMORY_API_KEY" \
  -d '{
    "agent_id": "openclaw",
    "workspace": "default",
    "query": "How do I run the local memory service?",
    "top_k": 5,
    "min_score": 0.25,
    "tags": ["docs"]
  }'
```

Delete an uploaded file from future search results:

```bash
curl -X DELETE \
  -H "X-API-Key: $MEMORY_API_KEY" \
  "http://127.0.0.1:8757/files/1?agent_id=openclaw&workspace=default"
```

Rebuild the combined memory and file FAISS index:

```bash
curl -X POST http://127.0.0.1:8757/files/reindex \
  -H "X-API-Key: $MEMORY_API_KEY"
```

## OpenClaw Tool Definitions

### openclaw_memory_add

```json
{
  "name": "openclaw_memory_add",
  "description": "Store durable long-term memory for future OpenClaw sessions.",
  "parameters": {
    "type": "object",
    "properties": {
      "agent_id": { "type": "string" },
      "workspace": { "type": "string" },
      "source": { "type": "string" },
      "memory_type": { "type": "string" },
      "content": { "type": "string" },
      "tags": { "type": "array", "items": { "type": "string" } },
      "importance": { "type": "number", "minimum": 0, "maximum": 1 }
    },
    "required": ["agent_id", "workspace", "source", "memory_type", "content", "tags", "importance"]
  }
}
```

### openclaw_memory_search

```json
{
  "name": "openclaw_memory_search",
  "description": "Retrieve relevant long-term semantic memories for the current OpenClaw task.",
  "parameters": {
    "type": "object",
    "properties": {
      "agent_id": { "type": "string" },
      "workspace": { "type": "string" },
      "query": { "type": "string" },
      "top_k": { "type": "integer", "minimum": 1, "maximum": 50 },
      "min_score": { "type": "number", "minimum": -1, "maximum": 1 },
      "tags": { "type": "array", "items": { "type": "string" } },
      "memory_type": { "type": "string" }
    },
    "required": ["agent_id", "workspace", "query", "top_k", "min_score"]
  }
}
```

### openclaw_memory_delete

```json
{
  "name": "openclaw_memory_delete",
  "description": "Delete a specific long-term memory by ID.",
  "parameters": {
    "type": "object",
    "properties": {
      "id": { "type": "integer" },
      "agent_id": { "type": "string" },
      "workspace": { "type": "string" }
    },
    "required": ["id", "agent_id", "workspace"]
  }
}
```

## OpenClaw Agent Prompt Section

Use BrainClaw as long-term memory.

Retrieve memory at the start of a task when the user request depends on prior preferences, project history, recurring workflows, long-running goals, or facts that may have been established in earlier sessions. Query using the current workspace, agent ID, and a concise semantic description of what you need.

Store memory only when information is likely to remain useful beyond the current task. Good candidates include stable user preferences, durable project decisions, architecture constraints, recurring commands, important environment details, and explicit instructions the user wants remembered.

Do not store secrets, credentials, API keys, private keys, access tokens, passwords, SSH keys, sensitive personal data, or transient implementation details that will not be useful later. Prefer short factual memories over full transcripts.

When memory appears outdated or wrong, update or delete it instead of adding conflicting duplicates.
