---
title: "Documentation Guidelines"
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-06
toc: true
---

# Documentation Guidelines

## Framework

- Diátaxis folders: `tutorials/`, `howto/`, `reference/`, `explanations/`.
- `.docs-policy.json` defines required front matter (title, doc_type, audience, product_area, last_verified, toc).
- Templates sourced from The Good Docs Project; ADRs follow MADR.

## Style

| Rule | Details |
|------|---------|
| Voice | Active, second person for How-to/Tutorials; descriptive for Reference/Explanation |
| Formatting | Use Markdown tables for structured data; code blocks with language hints |
| Terminology | Prefer "MarketDataDAL", "probabilistic agents", "Streamlit UI" |
| Linting | Vale optional (disabled per instruction) but keep sentences concise |

## Tutorial expectations

- Target outcome-driven stories (e.g., "Run breakout backtest"), not encyclopedic lists.
- Structure: Goal → Prerequisites → Step-by-step walkthrough → Troubleshooting/Next steps.
- Use real commands copied from scripts/CLI; annotate flags inline.
- Link to supporting How-to or Reference docs instead of duplicating long explanations.
- Update README documentation index whenever a new tutorial ships.

## Review checklist

- Include/update front matter with current `last_verified` date.
- Cross-link related docs using relative paths.
- Update README index when new top-level docs are added.
- Note sensitive plans in `research-docs/` (ignored from repo) rather than public docs.

## See also

- [Project README](../../README.md)
- [ADR 0001](../explanations/adr/0001-record-architecture-decisions.md)
