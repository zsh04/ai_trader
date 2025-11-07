---
title: "Create and Use Runbooks"
doc_type: how-to
audience: beginner
product_area: ops
last_verified: 2025-11-06
toc: true
---

# Create and Use Runbooks (How-to)

## Goal
Create incident runbooks that are executable and easy to follow.

## Steps
1) **Name and scope** — one runbook per incident class (e.g., “Broker outage”).
2) **Prechecks** — commands to confirm the symptom.
3) **Mitigation** — step-by-step actions; include rollbacks.
4) **Validation** — how to confirm recovery.
5) **Aftermath** — notes, ticket links, follow-ups.

## Template (copy)
```md
# <Runbook name>
Last reviewed: YYYY-MM-DD
Owner: @team

## Prechecks
- …

## Mitigation
- …

## Validation
- …

## Escalation
- On-call, vendor contacts
```

## Troubleshooting
If a step fails, record the exact output and proceed to escalation.

## Related
- [SRE & SLOs](../reference/sre-slos.md)
- [Deployment Environments](../explanations/platform/deployment-environments.md)
- [Security Model](../explanations/platform/security-model.md)
