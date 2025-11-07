---
title: "Deployment Environments"
doc_type: explanation
audience: beginner
product_area: ops
last_verified: 2025-11-06
toc: true
---

# Deployment Environments

## Rings and purpose
- **Dev:** fast iteration.
- **Paper:** production-like with simulated cash.
- **Live:** real capital, strict controls.

## Config matrix
List env vars/secrets that change by ring. Use feature flags to gate risky features.

## Promotion policy
- Entry/exit criteria, checks, and approvals.
- Shadow/canary before promotion.

## See also
- [SRE & SLOs](../reference/sre-slos.md)
- [Runbooks](../howto/runbooks.md)
- [System Architecture](./system-architecture.md)
