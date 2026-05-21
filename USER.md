# USER.md - About Your Human

This file is not the user memory database.

Use it only as a workspace default explaining how user facts must be handled. Store actual user profile facts, preferences, and durable notes in BrainClaw HTTP using the configured `OPENCLAW_AGENT_ID` and `OPENCLAW_WORKSPACE`.

## BrainClaw User Memory

For questions like:

- `what car do I have?`
- `where do I live?`
- `what do I prefer?`
- `what did I tell you before?`

Search BrainClaw HTTP first with focused terms and likely synonyms. If the search succeeds and no result is found, say no memory is recorded for that fact. If BrainClaw HTTP is unavailable, report the concrete HTTP/config error.

Do not inspect local notes or Markdown memory files as a fallback.

## Privacy

Never store secrets in BrainClaw. If the user asks you to remember a secret, remember only where it is configured or how it should be rotated.

## Related

- `OpenClaw.md`
- `AGENTS.md`
