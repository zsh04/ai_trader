---
title: "System Architecture"
doc_type: explanation
audience: intermediate
product_area: ops
last_verified: 2025-11-06
toc: true
---

# System Architecture

## Overview
State the system’s purpose, scope, and non-goals in 3–5 sentences.

## Component diagram
```mermaid
graph TD
  UI[Trader Console] --> API[API Gateway]
  API --> Bus[Event Bus]
  Bus --> Filter[SignalFiltering]
  Bus --> Regime[RegimeAnalysis]
  Regime --> Select[StrategySelection]
  Select --> Risk[RiskManagement]
  Risk --> Exec[ExecutionGateway]
  Exec --> Broker[Broker]
```

## Order lifecycle (sequence)
```mermaid
sequenceDiagram
  participant S as StrategySelection
  participant R as RiskManagement
  participant E as ExecutionGateway
  participant B as Broker
  S->>R: OrderIntent
  R->>E: RiskDecision(approved,size)
  E->>B: Place bracket order
  B-->>E: OrderAck/Fill
  E-->>S: Final status
```

## Non-functional requirements
List latency budgets, availability/SLOs, and scalability assumptions.

## Failure modes & resilience
Top failures and mitigations (retries, circuit breakers, kill switch, backpressure).

## Dependencies
Key external systems and contracts.

## See also
- [Database Architecture](../reference/database-architecture.md)
- [SRE & SLOs](../reference/sre-slos.md)
- [Deployment Environments](./deployment-environments.md)
