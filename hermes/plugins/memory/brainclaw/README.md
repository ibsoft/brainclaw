# BrainClaw Memory For Hermes

This plugin connects Hermes to BrainClaw through the HTTP API only.

Install path:

```text
hermes/plugins/memory/brainclaw/
```

Files:

- `__init__.py`: self-contained stdlib Python adapter.
- `plugin.yaml`: Hermes plugin metadata.
- `README.md`: usage and configuration notes.
- `Protocol.md`: provider contract, tool protocol, response format, and troubleshooting.
- `skills/brainclaw/SKILL.md`: reusable BrainClaw memory workflow skill.

## Configuration

The plugin first reads `/etc/hermes/environment.conf` when it exists and is readable. It then falls back to `/etc/openclaw/environment.conf`, then process environment variables.

Required:

- `BRAINCLAW_API_KEY` or `MEMORY_API_KEY`

Optional:

- `BRAINCLAW_URL`, configured here as `http://192.168.7.10:8757`
- `HERMES_AGENT_ID`, configured here as `CyberPhylax-7`
- `HERMES_WORKSPACE`, configured here as `CyberPhylax-Workspace`
- `HERMES_SYSTEM_PROMPT`
- `HERMES_DEFAULTS_DIR`
- `HERMES_WORKSPACE_DIR`

Fallback scope variables are also supported:

- `OPENCLAW_AGENT_ID`
- `OPENCLAW_WORKSPACE`
- `AGENT_ID`
- `WORKSPACE`

## Supported BrainClaw Endpoints

- `GET /health`
- `POST /memory/search`
- `POST /memory/add`
- `POST /memory/update`
- `POST /memory/delete`
- `POST /files/search`

The plugin does not use SQLite, FAISS files, Markdown memory files, or local embedded memory.

## Enable In Hermes

Copy or symlink this directory into Hermes' active plugin tree:

```bash
mkdir -p "$HERMES_HOME/plugins/memory"
ln -s /path/to/brainclaw/hermes/plugins/memory/brainclaw "$HERMES_HOME/plugins/memory/brainclaw"
```

Then select and configure it:

```bash
hermes memory setup
```

When prompted, choose `brainclaw` as the memory provider and set:

- `BRAINCLAW_API_KEY`
- `BRAINCLAW_URL`
- `HERMES_AGENT_ID`
- `HERMES_WORKSPACE`

If you already manage these values through `/etc/hermes/environment.conf` or environment variables, make sure Hermes can read them before startup.

Expected `/etc/hermes/environment.conf` shape:

```bash
BRAINCLAW_URL=http://192.168.7.10:8757
BRAINCLAW_API_KEY=<redacted>
HERMES_AGENT_ID=CyberPhylax-7
HERMES_WORKSPACE=CyberPhylax-Workspace
HERMES_SYSTEM_PROMPT=/etc/hermes/Hermes.md
HERMES_DEFAULTS_DIR=/etc/hermes/defaults
HERMES_WORKSPACE_DIR=/home/hermes/.hermes/workspace
```

## Python Usage

```python
from brainclaw import BrainClawMemory

memory = BrainClawMemory()
memory.health()
memory.search("project preferences", top_k=3, min_score=0.25)
memory.add(
    "Hermes uses BrainClaw HTTP memory only.",
    source="hermes-session",
    memory_type="project-fact",
    tags=["long", "hermes", "brainclaw"],
    importance=0.8,
)
```

If BrainClaw is unavailable, the adapter raises `BrainClawMemoryError` with the concrete HTTP or configuration failure.
