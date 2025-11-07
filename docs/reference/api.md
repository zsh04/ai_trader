---
title: "API Reference"
doc_type: reference
audience: intermediate
product_area: ops
last_verified: 2025-11-06
toc: true
---

# API Reference

## Synopsis
API Gateway endpoints and contracts.

## Auth
Bearer tokens (JWT) or API keys; scopes and roles.

## OpenAPI
Link/path to `openapi.yaml`.

## Endpoints
### POST /v1/orders
- **Body:** `OrderIntent`
- **201:** `OrderAck`
- **Errors:** `400`, `429`, `500`

### GET /v1/orders/{id}
- **200:** `OrderAck` + fills

## Rate limits & retries
State limits; backoff guidance for 429.

## Error model
`{ code, message, details }` with stable codes.

## See also
- [Data Models](./data-models.md)
- [SRE & SLOs](./sre-slos.md)
- [Architecture overview](../explanations/architecture/overview.md)
