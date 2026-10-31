# Observability

## Structured logs

Every log line from the application is one JSON object on stdout, so Docker collects it and any log tool (CloudWatch, Loki, ELK) can filter by field.

```json
{"time": "2026-10-30T20:23:40+0000", "level": "INFO", "message": "request", "version": "1.2.0",
 "request_id": "drill-001", "method": "GET", "path": "/tasks", "status": 500, "duration_ms": 1052.97}
```

- **request_id:** taken from the `X-Request-ID` header or generated; returned in the response header and in 500 error bodies, so one request can be traced end to end.
- **version** on every line, so errors can be tied to a release.
- Unhandled errors produce an extra `ERROR` line with `error_type` and a truncated message (200 chars) so stack details and data are not dumped into logs.
- Logs are in UTC.

Known gap: Uvicorn's own start-up lines are plain text.

## Health checks

| Check | Meaning | Used by |
|---|---|---|
| `/healthz` | Process is alive | Docker `HEALTHCHECK` (every 15 s, 3 failures = unhealthy), `restart: unless-stopped` |
| `/readyz` | Can do real work (database answers `SELECT 1`) | `deploy.sh` verification, CI smoke test; in Kubernetes it would gate traffic |
| `pg_isready` | Postgres accepts connections | Compose `depends_on: service_healthy` |

Liveness deliberately ignores the database: if the database is down, restarting the API would not help and would only hide the real cause.

## Metrics (`GET /metrics`, Prometheus format)

- `http_requests_total{method, path, status}`: counter
- `http_request_duration_seconds{path}`: histogram

`path` is the route template (`/tasks/{task_id}`), not the raw URL, to keep the number of series small.

## Alert proposal

Rules are in [`monitoring/alerts.yml`](../monitoring/alerts.yml). Prometheus would scrape `/metrics` every 15 s and Alertmanager would route alerts.

| Alert | Condition | Severity | First action |
|---|---|---|---|
| ApiDown | scrape fails for 2 min | page | `docker compose ps`, logs |
| HighErrorRate | 5xx > 5% of requests for 5 min | page | check `deploy.log`; roll back if after a deploy |
| HighLatencyP95 | p95 > 500 ms for 10 min | ticket | check DB, recent deploy |
| NotReady | `/readyz` failing for 2 min (blackbox probe) | page | database checks in runbook |

Thresholds are starting points, to be tuned against real traffic.

## Failure investigation: database outage drill

**Drill 1 (v1.0.0), 2026-10-30.** Stopped the database with `docker compose stop db`.

| Observation | Result |
|---|---|
| `/healthz` | 200 |
| `/readyz` | 503 `{"status":"not ready","dependency":"database"}` |
| `/tasks` | 500, plain text `Internal Server Error` |
| Logs | only `readiness check failed`; **no log line for the 500** |
| `/metrics` | **no 500 counted** |

**Finding:** an exception raised inside an endpoint propagated past the logging/metrics middleware. Users saw errors, but logs and metrics did not, so the proposed HighErrorRate alert could never fire during a real database outage.

**Fix (v1.2.0):** the middleware catches unhandled exceptions, logs them as JSON with the request ID, returns a JSON 500 that includes the request ID, and counts the request in metrics. A new test (`test_database_error_returns_500_and_is_counted`) fails on the old code and passes on the new.

**Drill 2 (v1.2.0), same day.** Same steps, request sent with `X-Request-ID: drill-001`:

- `/tasks` → `{"detail":"internal error","request_id":"drill-001"}` HTTP 500
- Logs: `ERROR unhandled error ... "error_type": "OperationalError", "error": "[Errno -2] Name or service not known"` plus the request line with `status: 500`
- `/metrics`: `http_requests_total{method="GET",path="/tasks",status="500"} 1.0`
- Recovery: `docker compose start db` → `/readyz` 200, data intact

Raw output: `evidence/05-db-outage-drill.txt`.
