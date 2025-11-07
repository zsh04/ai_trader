---
title: Phase 5 — knowledge and documentation
summary: Tracks the documentation strategy, tooling, and outstanding automation work.
status: current
last_updated: 2025-11-06
type: explanation
---

# Phase 5 — Knowledge & Documentation

Phase 5 ensures knowledge keeps pace with the codebase. Rather than aspirational automation diagrams, this section captures what exists today and what remains to systematise.

## Current Reality

- GitHub Actions enforce lint (`ruff`), security (`bandit`, `pip-audit`), and tests on every PR. Markdown lint/link pipelines are planned but not enabled.
- Project documentation lives in `/docs` while private planning artefacts reside in `research-docs/` (gitignored). Public-facing docs are now aligned with the DAL-first architecture.
- Codex/AI assistance is used interactively to draft code and docs, but there is no automated doc generation pipeline yet.
- Changelog management is manual (`CHANGELOG.md` in repo).

## Near-Term Goals

| Goal | Status | Notes |
|------|--------|-------|
| Documentation refresh | ✅ | README, secrets mapping, watchlist spec, architecture docs updated to reflect DAL/state. |
| Doc hygiene CI | 🟡 | Plan to add Markdown lint, link-check, and spell-check to the API workflow. |
| Knowledge consolidation | 🟡 | Research notes captured in `research-docs/`; need periodic roll-ups to Confluence. |
| Release communication | 🔘 | Automate changelog snippets + release announcements once execution goes live. |

## Operating Guidelines

- Treat documentation updates as part of the PR definition of done—especially when architectural changes land (DAL, vendors, risk modules).
- Keep `research-docs/` for private planning, but summarise material changes in the public docs to avoid institutional knowledge drift.
- Align README/roadmap/changelog version numbers with `app/__init__.__version__` and Git tags; update the changelog with every milestone.

## Future Enhancements

1. **Docs CI** — Introduce Markdown lint + link-check and ensure diagrams (if reintroduced) are generated during CI.
2. **Automated release notes** — Generate digest messages (Slack/Teams/email) from changelog diffs when tagging releases.
3. **Architecture snapshots** — Periodically export Streamlit/monitoring screenshots and embed them in the docs for traceability.
4. **Confluence sync** — Publish high-level summaries (roadmap, project progress, architecture) to the wider team after each phase completion.

Phase 5 will be considered complete once documentation changes are reviewed alongside code, CI enforces markdown hygiene, and release notes are produced automatically during deployments.
