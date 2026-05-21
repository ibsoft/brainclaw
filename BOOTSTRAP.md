# BOOTSTRAP.md - BrainClaw Startup

You just started a new OpenClaw session.

This workspace uses BrainClaw HTTP as the only memory system. Do not create or use Markdown memory files.

## Startup Procedure

Run this at the beginning of every session, including after `/new`:

1. Load `OpenClaw.md` if available.
2. Check whether `/etc/openclaw/environment.conf` exists.
3. If it exists and is readable, load it as shell-style environment configuration.
4. If it exists but is not readable, stop memory bootstrap and report: `BrainClaw environment config exists but is not readable`.
5. Fall back to process environment variables.
6. Default only missing non-secret values:

```bash
export BRAINCLAW_URL="${BRAINCLAW_URL:-http://127.0.0.1:8757}"
export BRAINCLAW_API_KEY="${BRAINCLAW_API_KEY:-${MEMORY_API_KEY:-}}"
export OPENCLAW_AGENT_ID="${OPENCLAW_AGENT_ID:-${AGENT_ID:-openclaw}}"
export OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-${WORKSPACE:-default}}"
```

7. Verify BrainClaw HTTP:

```bash
curl -sS -f -H "X-API-Key: $BRAINCLAW_API_KEY" "$BRAINCLAW_URL/health"
```

8. Search BrainClaw only when the current user request needs prior memory.

## Do Not Use

- local embedded memory
- local notes
- SQLite direct access
- FAISS direct access
- `MEMORY.md`
- `memory/YYYY-MM-DD.md`
- `memory.md`
- `memories.md`
- `.memory.md`

## Valid Statement

You may say `I checked BrainClaw` only after BrainClaw HTTP `/health` and the relevant BrainClaw HTTP search endpoint both returned HTTP 200.

If HTTP memory is unavailable, say:

```text
BrainClaw HTTP memory is unavailable: <specific HTTP/curl/config error>.
```

Do not fall back to another memory source.
