# HEARTBEAT.md - Periodic Checks

Keep this file empty, or with only comments, to skip heartbeat API calls.

When a heartbeat runs, do not use local embedded memory or Markdown memory files.

If memory is needed during a heartbeat:

1. Load `/etc/openclaw/environment.conf` if available.
2. Verify BrainClaw HTTP `/health`.
3. Use focused BrainClaw HTTP searches only.
4. Store only compact durable facts through BrainClaw HTTP.

Do not say memory was checked unless BrainClaw HTTP `/health` and the relevant HTTP search call both succeeded.

## Optional Checklist

Add small periodic tasks here only when the user asks.
