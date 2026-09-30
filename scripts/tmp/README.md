# scripts/tmp

One-off investigation scripts, smoke tests, and local CSV dumps. **Not imported by the web app** and not deployed as product features.

When fixing bugs or adding features, prefer `app/`, `core/`, and `tests/`. Only touch files here if a task explicitly references them.

Safe to delete obsolete probes after the related work is merged — nothing in CI depends on this folder.
