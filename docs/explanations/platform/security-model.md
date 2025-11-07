---
title: "Security Model"
doc_type: explanation
audience: intermediate
product_area: ops
last_verified: 2025-11-06
toc: true
---

# Security Model

## Threat model (summary)
Name key assets, entry points, and likely threats.

## Authentication & authorization
- AuthN method (OIDC, API keys).
- AuthZ model (RBAC/ABAC), least privilege.

## Data classification
- **Public** vs **Internal** docs and data.
- Handling rules for each class.

## Secrets management
- No secrets in code; storage and rotation policy.

## Audit & logging
- What is logged; retention; access controls.

## Third-party risk
Vendors, scopes, and review cadence.

## See also
- [API Reference](../reference/api.md)
- [Database Architecture](../reference/database-architecture.md)
