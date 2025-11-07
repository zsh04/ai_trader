---
title: "Data Models (Canonical Events)"
doc_type: reference
audience: intermediate
product_area: data
last_verified: 2025-11-06
toc: true
---

# Data Models (Canonical Events)

## Event catalog
`PriceBar`, `Quote`, `Signal`, `ProbVector`, `RiskDecision`, `OrderIntent`, `OrderAck`, `Fill`, `PnlUpdate`.

## Schemas (JSON)
```json
{
  "title": "OrderIntent",
  "type": "object",
  "required": ["symbol", "prob", "size"],
  "properties": {
    "symbol": {"type": "string"},
    "prob": {"type": "number", "minimum": 0, "maximum": 1},
    "size": {"type": "number", "minimum": 0},
    "meta": {"type": "object"}
  }
}
```

```json
{
  "title": "RiskDecision",
  "type": "object",
  "required": ["approved", "cappedSize", "reason"],
  "properties": {
    "approved": {"type": "boolean"},
    "cappedSize": {"type": "number", "minimum": 0},
    "reason": {"type": "string"}
  }
}
```

(Add remaining events as needed.)

## Versioning & compatibility
- Prefer additive, backward-compatible changes
- Use `meta.version` when breaking; support dual writes during migration

## See also
- [API Reference](./api.md)
- [Architecture overview](../explanations/architecture/overview.md)
