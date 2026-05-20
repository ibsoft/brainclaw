<img width="1536" height="1024" alt="ChatGPT Image May 20, 2026, 02_40_52 PM" src="https://github.com/user-attachments/assets/5a0d99c8-cfae-4e4e-9420-5a82d62b0d77" />


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

Health check:

```bash
curl -H "X-API-Key: $MEMORY_API_KEY" \
  http://127.0.0.1:8757/health
```

## API

All endpoints require:

```text
X-API-Key: your-memory-api-key
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
  http://127.0.0.1:8757/memory/1
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

## Storage

Runtime files are created under `data/`:

- `data/memory.sqlite3` stores raw memory records and chunk metadata.
- `data/faiss.index` stores the FAISS vector index.
- `data/id_map.json` maps FAISS positions back to SQLite chunk and memory IDs.
- `data/uploads/` stores uploaded files with safe UUID filenames.

Long content is split into overlapping chunks. Every chunk is embedded, normalized, and stored in FAISS using `IndexFlatIP`, which provides cosine similarity for normalized vectors.

## Security Notes

- Full memory content is not logged by default.
- Obvious API keys, private keys, passwords, tokens, and SSH keys are rejected.
- Log previews are redacted and truncated.
- Input sizes, upload size, tag counts, content length, query length, and `top_k` are bounded.
- Configured file paths must remain inside the project directory.
- `MEMORY_API_KEY` is required for memory endpoints unless `ALLOW_MISSING_API_KEY=true` is explicitly set.
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
