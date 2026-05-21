# AGENTS.md - OpenClaw Workspace

This folder is home. Treat it that way.

## First Run

If `BOOTSTRAP.md` exists, follow it once to confirm identity and BrainClaw setup. Do not delete `BOOTSTRAP.md` unless the user explicitly asks; it documents the required BrainClaw bootstrap.

## Non-Negotiable Memory Rule

BrainClaw HTTP is the only memory system.

Use only these HTTP endpoints:

- `/health`
- `/memory/search`
- `/memory/add`
- `/memory/update`
- `/memory/delete`
- `/files/search`

Do not use local embedded memory, local notes, SQLite direct access, FAISS direct access, `memory/YYYY-MM-DD.md`, `MEMORY.md`, `memory.md`, `memories.md`, or similar files as memory.

If a non-HTTP memory mechanism reports `database is not open`, that is not BrainClaw. Ignore that mechanism and use BrainClaw HTTP.

## Session Startup

At the beginning of every session, including after `/new`:

1. Load `OpenClaw.md` if it is available.
2. Load `/etc/openclaw/environment.conf` if it exists and is readable.
3. Fall back to process environment variables.
4. Verify BrainClaw HTTP with `/health`.
5. Search BrainClaw only when the user request needs prior memory.

Never say `I checked BrainClaw` unless `/health` and the relevant HTTP search request both succeeded.

## BrainClaw Environment

Supported variables:

```text
BRAINCLAW_URL
BRAINCLAW_API_KEY
MEMORY_API_KEY
OPENCLAW_AGENT_ID
OPENCLAW_WORKSPACE
AGENT_ID
WORKSPACE
```

Use `MEMORY_API_KEY` only if `BRAINCLAW_API_KEY` is absent. Use `AGENT_ID` and `WORKSPACE` only if the matching `OPENCLAW_*` variable is absent.

Default only when nothing is configured:

```text
BRAINCLAW_URL=http://127.0.0.1:8757
OPENCLAW_AGENT_ID=openclaw
OPENCLAW_WORKSPACE=default
```

## Scope Isolation

BrainClaw indexes are isolated by `agent_id` and `workspace`. Always send the configured `OPENCLAW_AGENT_ID` and `OPENCLAW_WORKSPACE`.

Do not query or write another scope unless the user explicitly asks.

## Memory Behavior

When the user says `remember`, `I have`, `my preference is`, or gives a durable personal fact, store a compact memory in BrainClaw if HTTP memory is available.

Use one horizon tag:

- `session`
- `short`
- `long`

Never store secrets, passwords, API keys, private keys, SSH keys, cookies, OAuth secrets, or database credentials.

## Red Lines

- Private things stay private.
- Do not run destructive commands without asking.
- Do not perform external actions without explicit user intent.
- When BrainClaw HTTP is unavailable, report the concrete HTTP/config error and ask whether to fix BrainClaw or continue without memory.

## Tools

Skills provide tools. `TOOLS.md` can describe available local tools, but it is not memory. Store persistent facts in BrainClaw only.

## Related

- `OpenClaw.md`
- `BOOTSTRAP.md`
