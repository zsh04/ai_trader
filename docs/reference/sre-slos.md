---
title: "SRE & SLOs"
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-06
toc: true
---

# SRE & SLOs

## Service Level Objectives
| SLI                          | SLO        | Measure                     |
|-----------------------------|------------|-----------------------------|
| Order path availability     | 99.9%/30d  | Success rate on /orders     |
| Decision latency (p99)      | < 30 ms    | Trace timers                |
| Broker RTT (p99)            | < 150 ms   | ExecGateway timers          |
| Data completeness (market)  | ≥ 99.95%   | Ingest counters             |

## Alerting policy
- Multi-window, multi-burn rate alerts.
- Paging routes and escalation.

## Error budgets & releases
How budgets govern deploy velocity.

## See also
- [Architecture overview](../explanations/architecture/overview.md)
- [Operations runbook](../howto/operations/runbook.md)
- [Deployment environments](../explanations/platform/deployment-environments.md)
