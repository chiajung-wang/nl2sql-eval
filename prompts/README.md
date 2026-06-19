# Version-controlled prompt templates (prompt-CI diffs this dir)

Externalized, version-controlled Jinja templates — never inline prompt strings
in Python (CLAUDE.md §4). The prompt-CI workflow (Step 9) diffs this directory
and re-runs the eval whenever a template changes.

## Structure (clean CI diffs)

Templates are structured so the **static scaffold stays put** and only a
meaningful edit shows in a diff:

- `generate/_base.jinja` — the shared static scaffold (the dialect-aware NL→SQL
  prompt body). It exposes `{% block %}`s for the parts a version changes
  (e.g. `rules`).
- `generate/vN.jinja` — a **thin version file** that `{% extends %}` the
  scaffold and overrides only the blocks it changes. The active version
  (`v3`) carries no overrides; a future `v4` is a few lines overriding one
  block — a tight diff, not a 35-line whole-file rewrite.
- `generate/v1.jinja`, `generate/v2.jinja` — frozen history (Step 1 / Step 3),
  kept verbatim as the version record.

## Version + fingerprint (pin a number to its prompt)

`nl2sql.prompts` is the single source of truth: it loads templates, names the
active version, and fingerprints the active template **plus the partials it
extends** so a number always traces to the exact prompt bytes (CLAUDE.md §6).

```
python -m nl2sql.prompts --version       # -> generate/v3
python -m nl2sql.prompts --fingerprint   # -> sha256:...  (covers _base.jinja too)
```

`RESULTS.md` rows pin the version; prompt-CI pins the fingerprint (a version
string can be left stale by an in-place edit — the fingerprint cannot).
