# Task Management API — Design Specification

## 1. Overview

RESTful HTTP API for a multi-user task tracker. JSON over HTTPS, Bearer-token
auth, resource-scoped access. The API is **versioned under `/api/v1`**.

## 2. Goals & non-functional requirements

| Concern            | Requirement                                                               |
|--------------------|---------------------------------------------------------------------------|
| Correctness        | Strong validation; single consistent error envelope                       |
| Latency            | p95 < 300 ms for list/create; all reads cacheable with ETag               |
| Availability       | Stateless API nodes; retries safe (idempotency keys on writes)            |
| Evolvability       | Semantic versioning; additive changes only within a version               |
| Observability      | `X-Request-Id` on every request and echoed in every error                 |

## 3. Authentication

- **Scheme**: `Authorization: Bearer <token>` (OAuth2, opaque JWT).
- **Scopes**: `tasks:read`, `tasks:write`, `admin`.
- Missing/invalid token -> `401`; authenticated-but-not-allowed -> `403`.
- Tokens expire (default 1h); refresh via the token endpoint (out of scope here).

## 4. Resource model

### Task

| Field        | Type      | Constraints                | Notes                    |
|--------------|-----------|----------------------------|--------------------------|
| `id`         | uuid      | server-assigned            | stable, never reused     |
| `title`      | string    | 1..120 chars, required     | trimmed, not blank       |
| `description`| string    | 0..2000 chars              | optional                 |
| `status`     | enum      | `todo`/`in_progress`/`done`| default `todo`           |
| `priority`   | enum      | `low`/`normal`/`high`      | default `normal`         |
| `assignee_id`| uuid?     | nullable user id           | must reference a user    |
| `due_at`     | iso8601?  | nullable                   | UTC; `>= now` on create  |
| `created_at` | iso8601   | server-set                 | immutable                |
| `updated_at` | iso8601   | server-set                 | bumped on every write    |

### Transitions

```
todo --(start)--> in_progress --(complete)--> done
todo --(complete)--> done
done --(reopen)--> todo
```
Any other transition -> `409 conflict` with a machine-readable `code`.

## 5. Endpoints

### 5.1 List tasks — `GET /api/v1/tasks`

Query params: `status`, `priority`, `assignee_id`, `due_before`, `cursor`, `limit` (1..100, default 25).

Response `200`:

```json
{
  "data": [ { "id": "...", "title": "Ship docs", "status": "in_progress" } ],
  "next": "cursor-value-or-null",
  "count": 25
}
```

### 5.2 Create task — `POST /api/v1/tasks`

Request:

```json
{ "title": "Write spec", "description": "...", "priority": "high", "due_at": "2026-01-15T12:00:00Z" }
```

Response `201` with `Location: /api/v1/tasks/{id}`.
Invalid body -> `400` with `details[]` naming each field.

### 5.3 Get task — `GET /api/v1/tasks/{id}`

`200` full representation, `404` with `{ "error": { "code": "not_found", ... } }`.
Supports `If-None-Match` -> `304`.

### 5.4 Update task — `PATCH /api/v1/tasks/{id}`

Partial update; only supplied fields change. `updated_at` always bumped.
Illegal status transition -> `409`.

### 5.5 Delete task — `DELETE /api/v1/tasks/{id}`

`204` on success; `404` if missing. Idempotent: repeated delete of a deleted
resource returns `404` (not `204`), so clients use the response to detect races.

## 6. Error contract

Single envelope, every error:

```json
{
  "error": {
    "code": "validation_failed",
    "message": "2 validation errors",
    "details": [ { "field": "due_at", "reason": "must be in the future" } ],
    "request_id": "req_9f8a..."
  }
}
```

| Code                  | HTTP  | Meaning                                    |
|-----------------------|-------|--------------------------------------------|
| `validation_failed`   | 400   | Malformed body or query                    |
| `unauthorized`        | 401   | Missing/invalid token                      |
| `forbidden`           | 403   | Valid token, insufficient scope            |
| `not_found`           | 404   | Resource absent                            |
| `conflict`            | 409   | State/version conflict                     |
| `rate_limited`        | 429   | Quota exceeded, honor `Retry-After`        |
| `internal_error`      | 500   | Unexpected; never leak stack traces        |

## 7. Pagination

Cursor-based. `next` is an opaque token; clients must never construct it.
`limit` caps page size; cursor pages are stable under concurrent writes.

## 8. Versioning

Path-based (`/api/v1`). Backwards-incompatible changes require `v2`. New fields
may be added within a version; clients must ignore unknown fields.

## 9. Rate limiting

- Per token: 120 req/min, burst 20. Headers: `X-RateLimit-Limit`,
  `X-RateLimit-Remaining`, `X-RateLimit-Reset`. Exceeding -> `429` +
  `Retry-After`.

## 10. Security & operational notes

- TLS everywhere; HSTS header set.
- `X-Request-Id` generated upstream, echoed on all responses/errors.
- Audit log records every write: actor id, resource, before/after.
- Logs redact tokens and personal data.
