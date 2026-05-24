# BrainClaw Hermes Memory Plugin Protocol

This document defines the runtime contract between Hermes, the `brainclaw` memory provider plugin, and the BrainClaw HTTP API.

## Purpose

The plugin makes BrainClaw the memory provider for the Hermes agent. BrainClaw is accessed only through HTTP. The plugin must not read or write SQLite directly, inspect FAISS files, or use Markdown memory files as a memory source.

## Files

```text
hermes/plugins/memory/brainclaw/
├── __init__.py
├── plugin.yaml
├── README.md
└── Protocol.md
```

## Hermes Plugin Contract

Hermes discovers this plugin from a memory plugin directory named `brainclaw`.

`plugin.yaml` is intentionally minimal:

```yaml
name: brainclaw
version: 0.1.0
description: "HTTP-only BrainClaw memory provider for the Hermes agent."
hooks: []
```

`__init__.py` must expose:

- `BrainClawMemoryProvider`
- `register(ctx)`

`register(ctx)` registers the provider:

```python
ctx.register_memory_provider(BrainClawMemoryProvider())
```

The provider implements the Hermes memory provider methods:

- `name`
- `is_available()`
- `initialize(session_id, **kwargs)`
- `get_config_schema()`
- `system_prompt_block()`
- `get_tool_schemas()`
- `handle_tool_call(tool_name, args, **kwargs)`

## Availability

`is_available()` checks configuration only. It does not call the BrainClaw network service. Hermes can call availability checks during startup or setup, so this method must stay fast and side-effect free.

The provider is available when:

- `/etc/hermes/environment.conf` is absent or readable.
- `BRAINCLAW_API_KEY` or `MEMORY_API_KEY` is configured.

Actual HTTP availability is verified only when a tool call reaches BrainClaw.

## Configuration Resolution

The plugin loads configuration in this order:

1. `/etc/hermes/environment.conf`, if it exists and is readable.
2. `/etc/openclaw/environment.conf`, if it exists and is readable.
3. Process environment variables.
4. Built-in defaults for non-secret values.

If either environment file exists but is not readable, configuration fails with the path in the error.

Supported variables:

```text
BRAINCLAW_URL
BRAINCLAW_API_KEY
MEMORY_API_KEY
HERMES_AGENT_ID
HERMES_WORKSPACE
HERMES_SYSTEM_PROMPT
HERMES_DEFAULTS_DIR
HERMES_WORKSPACE_DIR
OPENCLAW_AGENT_ID
OPENCLAW_WORKSPACE
AGENT_ID
WORKSPACE
```

Expected `/etc/hermes/environment.conf` for this host:

```bash
BRAINCLAW_URL=http://192.168.7.10:8757
BRAINCLAW_API_KEY=<redacted>
HERMES_AGENT_ID=CyberPhylax-7
HERMES_WORKSPACE=CyberPhylax-Workspace
HERMES_SYSTEM_PROMPT=/etc/hermes/Hermes.md
HERMES_DEFAULTS_DIR=/etc/hermes/defaults
HERMES_WORKSPACE_DIR=/home/hermes/.hermes/workspace
```

Resolution rules:

```text
BRAINCLAW_URL         -> BrainClaw base URL, default http://127.0.0.1:8757
BRAINCLAW_API_KEY     -> X-API-Key value
MEMORY_API_KEY        -> X-API-Key value when BRAINCLAW_API_KEY is absent
HERMES_AGENT_ID       -> BrainClaw agent_id, default hermes
HERMES_WORKSPACE      -> BrainClaw workspace, default default
HERMES_SYSTEM_PROMPT  -> Hermes prompt file; ignored by the memory adapter
HERMES_DEFAULTS_DIR   -> Hermes defaults directory; ignored by the memory adapter
HERMES_WORKSPACE_DIR  -> Hermes workspace directory; ignored by the memory adapter
OPENCLAW_AGENT_ID     -> fallback agent_id
OPENCLAW_WORKSPACE    -> fallback workspace
AGENT_ID              -> fallback agent_id
WORKSPACE             -> fallback workspace
```

Hermes-specific prompt/workspace variables may exist in the file and are ignored by the memory adapter:

```text
HERMES_SYSTEM_PROMPT
HERMES_DEFAULTS_DIR
HERMES_WORKSPACE_DIR
```

Secrets must not be printed.

## BrainClaw Scope

Every memory request includes:

```json
{
  "agent_id": "<configured agent id>",
  "workspace": "<configured workspace>"
}
```

BrainClaw isolates API keys and indexes by `agent_id` and `workspace`. If an API key is scoped to `openclaw/default`, requests for `CyberPhylax-7/CyberPhylax-Workspace` will fail with HTTP 403.

Recommended Hermes scope:

```text
HERMES_AGENT_ID=CyberPhylax-7
HERMES_WORKSPACE=CyberPhylax-Workspace
```

If the available key is scoped differently, configure Hermes to use the same scope as the key.

## HTTP Transport

All requests use:

```text
X-API-Key: <BRAINCLAW_API_KEY or MEMORY_API_KEY>
Content-Type: application/json
```

The plugin uses these BrainClaw endpoints:

- `GET /health`
- `POST /memory/search`
- `POST /memory/add`
- `POST /memory/update`
- `POST /memory/delete`
- `POST /files/search`

The Hermes tool layer currently exposes search, add, and file search. The lower-level adapter also provides health, update, and delete methods.

## Response Envelope

BrainClaw API responses use JSON status envelopes.

Successful write actions return:

```json
{
  "status": "success",
  "ok": true,
  "id": 123,
  "message": "memory added",
  "details": {
    "chunks": 1
  }
}
```

Successful searches return:

```json
{
  "status": "success",
  "ok": true,
  "count": 1,
  "results": []
}
```

Failures return:

```json
{
  "status": "failure",
  "ok": false,
  "message": "API key is not allowed for this agent/workspace",
  "details": {}
}
```

Hermes tool calls return a JSON string. On plugin-side exceptions, the return shape is:

```json
{
  "ok": false,
  "error": "<specific error>"
}
```

## Tool Protocol

Hermes receives these tool schemas when the provider is initialized.

### `brainclaw_search`

Search normal BrainClaw memory in the configured Hermes scope.

Required:

- `query`

Optional:

- `top_k`, default `3`
- `min_score`, default `0.25`
- `tags`
- `memory_type`

Request sent to BrainClaw:

```json
{
  "agent_id": "CyberPhylax-7",
  "workspace": "CyberPhylax-Workspace",
  "query": "project preferences",
  "top_k": 3,
  "min_score": 0.25,
  "tags": ["long"],
  "memory_type": "user-preference"
}
```

Endpoint:

```text
POST /memory/search
```

### `brainclaw_add`

Add compact non-secret memory to the configured Hermes scope.

Required:

- `content`

Optional:

- `source`, default `hermes-session`
- `memory_type`, default `note`
- `tags`, default `["short", "hermes"]`
- `importance`, default `0.5`

Request sent to BrainClaw:

```json
{
  "agent_id": "CyberPhylax-7",
  "workspace": "CyberPhylax-Workspace",
  "source": "hermes-session",
  "memory_type": "project-fact",
  "content": "Hermes uses BrainClaw HTTP memory only.",
  "tags": ["long", "hermes", "brainclaw"],
  "importance": 0.8
}
```

Endpoint:

```text
POST /memory/add
```

### `brainclaw_files_search`

Search uploaded document memory in the configured Hermes scope.

Required:

- `query`

Optional:

- `top_k`, default `3`
- `min_score`, default `0.25`
- `tags`

Request sent to BrainClaw:

```json
{
  "agent_id": "CyberPhylax-7",
  "workspace": "CyberPhylax-Workspace",
  "query": "deployment instructions",
  "top_k": 3,
  "min_score": 0.25
}
```

Endpoint:

```text
POST /files/search
```

## Memory Write Rules

The plugin is designed for compact, durable memory.

Store:

- Stable user preferences.
- Project facts.
- Implementation decisions.
- Useful recurring workflows.
- Non-obvious debugging outcomes.

Do not store:

- API keys.
- Passwords.
- Access tokens.
- Private keys.
- Session cookies.
- Full logs.
- Full transcripts.
- Large files.

Use exactly one horizon tag:

- `session`
- `short`
- `long`

Additional topical tags are allowed, for example:

```json
["long", "hermes", "brainclaw"]
```

## Enabling The Plugin

Place the plugin in Hermes' active plugin tree:

```bash
mkdir -p "$HERMES_HOME/plugins/memory"
ln -s /home/ioannisb/Development/brainclaw/hermes/plugins/memory/brainclaw \
  "$HERMES_HOME/plugins/memory/brainclaw"
```

Run Hermes memory setup:

```bash
hermes memory setup
```

Choose:

```text
brainclaw
```

Set or export:

```bash
export BRAINCLAW_URL=http://192.168.7.10:8757
export BRAINCLAW_API_KEY=<brainclaw-key>
export HERMES_AGENT_ID=CyberPhylax-7
export HERMES_WORKSPACE=CyberPhylax-Workspace
export HERMES_SYSTEM_PROMPT=/etc/hermes/Hermes.md
export HERMES_DEFAULTS_DIR=/etc/hermes/defaults
export HERMES_WORKSPACE_DIR=/home/hermes/.hermes/workspace
```

If using `/etc/hermes/environment.conf`, make sure the Hermes process can read it.

## Troubleshooting

### HTTP 401

The API key is missing or invalid.

Check:

```bash
echo "${BRAINCLAW_API_KEY:+set}"
echo "${MEMORY_API_KEY:+set}"
```

Do not print the actual key.

### HTTP 403

The key is valid but not allowed for the requested scope.

The request scope must match the key scope:

```text
agent_id + workspace
```

For example, a key for `openclaw/default` cannot write to `CyberPhylax-7/CyberPhylax-Workspace`.

### Search returns zero results

Check:

- The memory was inserted under the same `agent_id` and `workspace`.
- `min_score` is not too high.
- Tags are not filtering out the result.
- The BrainClaw FAISS index has been rebuilt after embedding or isolation changes.

### Curl hides the JSON error

Avoid `curl -f` while debugging. Use:

```bash
curl -sS -X POST "$BRAINCLAW_URL/memory/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BRAINCLAW_API_KEY" \
  -d '{"agent_id":"CyberPhylax-7","workspace":"CyberPhylax-Workspace","query":"test","top_k":3,"min_score":0.25}'
```

## Manual Verification

Health:

```bash
curl -sS -H "X-API-Key: $BRAINCLAW_API_KEY" "$BRAINCLAW_URL/health"
```

Add:

```bash
curl -sS -X POST "$BRAINCLAW_URL/memory/add" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BRAINCLAW_API_KEY" \
  -d '{
    "agent_id": "CyberPhylax-7",
    "workspace": "CyberPhylax-Workspace",
    "source": "manual-test",
    "memory_type": "note",
    "content": "Hermes BrainClaw plugin manual verification memory.",
    "tags": ["short", "hermes", "manual"],
    "importance": 0.5
  }'
```

Search:

```bash
curl -sS -X POST "$BRAINCLAW_URL/memory/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BRAINCLAW_API_KEY" \
  -d '{
    "agent_id": "CyberPhylax-7",
    "workspace": "CyberPhylax-Workspace",
    "query": "manual verification memory",
    "top_k": 3,
    "min_score": 0.25
  }'
```
