---
name: brainclaw
description: Use when working with BrainClaw HTTP memory for Hermes or other agents, including checking memory availability, searching memories, adding/updating/deleting memories, searching uploaded document memory, troubleshooting API key scope errors, or configuring /etc/hermes/environment.conf.
---

# BrainClaw Memory

Use BrainClaw only through the HTTP API. Do not read SQLite, FAISS files, Markdown memory files, local notes, or embedded memory as a BrainClaw substitute.

## Core Rule

You may say BrainClaw was checked only after both succeed:

1. `GET /health`
2. The relevant search endpoint, usually `POST /memory/search` or `POST /files/search`

If the API is unavailable, report the concrete HTTP, curl, or configuration error. Do not fall back to another memory source.

## Configuration

Load configuration in this order:

1. `/etc/hermes/environment.conf`
2. `/etc/openclaw/environment.conf`
3. Process environment variables
4. Defaults for non-secret values

Required secret:

- `BRAINCLAW_API_KEY`, or `MEMORY_API_KEY` if `BRAINCLAW_API_KEY` is absent

Scope variables:

- `HERMES_AGENT_ID`
- `HERMES_WORKSPACE`
- `OPENCLAW_AGENT_ID`
- `OPENCLAW_WORKSPACE`
- `AGENT_ID`
- `WORKSPACE`

Default scope:

```text
agent_id=hermes
workspace=default
```

Current Hermes deployment convention:

```text
BRAINCLAW_URL=http://192.168.7.10:8757
HERMES_AGENT_ID=CyberPhylax-7
HERMES_WORKSPACE=CyberPhylax-Workspace
HERMES_SYSTEM_PROMPT=/etc/hermes/Hermes.md
HERMES_DEFAULTS_DIR=/etc/hermes/defaults
HERMES_WORKSPACE_DIR=/home/hermes/.hermes/workspace
```

Never print API keys or other secrets.

## Endpoints

Use only these BrainClaw memory endpoints:

- `GET /health`
- `POST /memory/search`
- `POST /memory/add`
- `POST /memory/update`
- `POST /memory/delete`
- `POST /files/search`

## Search Workflow

1. Verify `/health`.
2. Search the exact configured `agent_id` and `workspace`.
3. Use a focused query, `top_k: 3`, and `min_score: 0.25` by default.
4. If no useful result is found, try one broader query in the same scope.
5. If document memory may matter, search `/files/search`.

Example:

```bash
curl -sS -X POST "$BRAINCLAW_URL/memory/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BRAINCLAW_API_KEY" \
  -d '{
    "agent_id": "'"$HERMES_AGENT_ID"'",
    "workspace": "'"$HERMES_WORKSPACE"'",
    "query": "project preferences",
    "top_k": 3,
    "min_score": 0.25
  }'
```

## Add Memory Workflow

Store only compact, durable, non-secret facts.

Use exactly one horizon tag:

- `session`
- `short`
- `long`

Recommended fields:

```json
{
  "source": "hermes-session",
  "memory_type": "project-fact",
  "content": "Compact durable fact.",
  "tags": ["long", "hermes"],
  "importance": 0.8
}
```

Do not store API keys, passwords, tokens, private keys, session cookies, full logs, full transcripts, or large files.

## Response Handling

BrainClaw returns JSON envelopes.

Success:

```json
{
  "status": "success",
  "ok": true
}
```

Failure:

```json
{
  "status": "failure",
  "ok": false,
  "message": "specific error",
  "details": {}
}
```

Avoid `curl -f` while debugging because it hides the JSON error body.

## Troubleshooting

HTTP 401 means the API key is missing or invalid.

HTTP 403 means the key is valid but not authorized for the requested `agent_id` and `workspace`. The request scope must match the key scope exactly.

Empty search results usually mean one of:

- Memory was stored in a different scope.
- `min_score` is too high.
- Tags or `memory_type` filtered the result out.
- Indexes need to be rebuilt after isolation or embedding changes.

## References

For the full Hermes plugin contract, environment file shape, tool schemas, and manual verification commands, read:

```text
hermes/plugins/memory/brainclaw/Protocol.md
```
