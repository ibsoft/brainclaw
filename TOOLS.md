# TOOLS.md - Local Tool Notes

Skills define how tools work. This file describes the BrainClaw HTTP tool contract for this workspace.

This file is not memory. Do not store remembered facts here.

## BrainClaw HTTP

Required environment:

```text
BRAINCLAW_URL
BRAINCLAW_API_KEY
OPENCLAW_AGENT_ID
OPENCLAW_WORKSPACE
```

Load these from `/etc/openclaw/environment.conf` when available. If `BRAINCLAW_API_KEY` is absent, use `MEMORY_API_KEY`.

Health check:

```bash
curl -sS -f -H "X-API-Key: $BRAINCLAW_API_KEY" "$BRAINCLAW_URL/health"
```

Search memory:

```bash
curl -sS -f -X POST "$BRAINCLAW_URL/memory/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BRAINCLAW_API_KEY" \
  -d '{
    "agent_id": "'"$OPENCLAW_AGENT_ID"'",
    "workspace": "'"$OPENCLAW_WORKSPACE"'",
    "query": "focused search terms",
    "top_k": 3,
    "min_score": 0.25
  }'
```

Search uploaded documents:

```bash
curl -sS -f -X POST "$BRAINCLAW_URL/files/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BRAINCLAW_API_KEY" \
  -d '{
    "agent_id": "'"$OPENCLAW_AGENT_ID"'",
    "workspace": "'"$OPENCLAW_WORKSPACE"'",
    "query": "focused document search terms",
    "top_k": 3,
    "min_score": 0.25
  }'
```

## Rule

Only BrainClaw HTTP counts as BrainClaw. Local embedded memory, SQLite direct access, FAISS direct access, and Markdown files are not BrainClaw.
