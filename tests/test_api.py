"""Automated checks for the Apex Operations API.

They run against the in-memory store (DATABASE_URL defaults to memory://),
so they need no database and run the same way on a laptop and in CI.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


# 1. Liveness
def test_healthz_returns_ok():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# 2. Readiness when the dependency is up
def test_readyz_ready_when_store_is_up():
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


# 3. Readiness when the dependency is down -> 503 (simulated outage)
def test_readyz_returns_503_when_store_is_down(monkeypatch):
    monkeypatch.setattr(main.store, "is_ready", lambda: False)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["dependency"] == "database"


# 4. Create a task
def test_create_task_returns_201_and_the_task():
    r = client.post("/tasks", json={"title": "Rotate logs", "priority": "high"})
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Rotate logs"
    assert body["priority"] == "high"
    assert body["status"] == "open"


# 5. Created task can be read back
def test_created_task_can_be_fetched_by_id():
    created = client.post("/tasks", json={"title": "Patch servers"}).json()
    r = client.get(f"/tasks/{created['id']}")
    assert r.status_code == 200
    assert r.json()["priority"] == "medium"  # default priority


# 6. Unknown task -> 404
def test_unknown_task_returns_404():
    r = client.get("/tasks/999999")
    assert r.status_code == 404


# 7. Input validation: bad priority rejected
def test_invalid_priority_is_rejected_with_422():
    r = client.post("/tasks", json={"title": "Fix DB", "priority": "urgent"})
    assert r.status_code == 422


# 8. Input validation: empty title rejected
def test_empty_title_is_rejected_with_422():
    r = client.post("/tasks", json={"title": ""})
    assert r.status_code == 422


# 9. Metrics endpoint exposes request counters
def test_metrics_exposes_request_counter():
    client.get("/healthz")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text


# 10. Every response carries a request ID for log tracing
def test_response_has_request_id_header():
    r = client.get("/healthz", headers={"X-Request-ID": "trace-123"})
    assert r.headers["X-Request-ID"] == "trace-123"


# 11. INTENTIONAL FAILURE (demo). Skipped normally.
#     Set FAIL_DEMO=1 to make it run and fail, proving CI blocks the release.
@pytest.mark.skipif(os.getenv("FAIL_DEMO") != "1", reason="set FAIL_DEMO=1 to run the failure demo")
def test_intentional_failure_demo():
    r = client.get("/healthz")
    assert r.json() == {"status": "this-will-never-match"}, "Intentional failure: CI must block the release"


# 12. v1.1.0 feature: close a task
def test_close_task_sets_status_closed():
    created = client.post("/tasks", json={"title": "Renew TLS cert"}).json()
    r = client.post(f"/tasks/{created['id']}/close")
    assert r.status_code == 200
    assert r.json()["status"] == "closed"
    assert client.post("/tasks/999999/close").status_code == 404


# 13. Database errors are logged, counted in metrics and return a clean 500
def test_database_error_returns_500_and_is_counted(monkeypatch):
    def broken():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(main.store, "list_tasks", broken)
    r = client.get("/tasks", headers={"X-Request-ID": "db-down-1"})
    assert r.status_code == 500
    assert r.json()["request_id"] == "db-down-1"
    metrics = client.get("/metrics").text
    assert 'path="/tasks",status="500"' in metrics
