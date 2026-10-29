"""Apex Operations API: a small service for tracking operational tasks."""

import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from app.store import build_store

APP_VERSION = os.getenv("APP_VERSION", "dev")
DATABASE_URL = os.getenv("DATABASE_URL", "memory://")


# ---------- Structured (JSON) logging ----------
class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "message": record.getMessage(),
            "version": APP_VERSION,
        }
        entry.update(getattr(record, "extra_fields", {}))
        return json.dumps(entry)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
log = logging.getLogger("apex")
log.handlers = [handler]
log.setLevel(os.getenv("LOG_LEVEL", "INFO"))
log.propagate = False


# ---------- Metrics (Prometheus format) ----------
REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["path"])


# ---------- App start-up ----------
store = build_store(DATABASE_URL)


@asynccontextmanager
async def lifespan(app):
    try:
        store.init_schema()
        log.info("startup complete", extra={"extra_fields": {"event": "startup"}})
    except Exception as exc:  # the app still starts; /readyz will report not ready
        log.error("schema init failed", extra={"extra_fields": {"error": str(exc)}})
    yield


app = FastAPI(title="Apex Operations API", version=APP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    route = request.scope.get("route")
    path = route.path if route else "unmatched"
    REQUESTS.labels(request.method, path, response.status_code).inc()
    LATENCY.labels(path).observe(duration)
    response.headers["X-Request-ID"] = request_id
    log.info(
        "request",
        extra={"extra_fields": {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration * 1000, 2),
        }},
    )
    return response


# ---------- Health and operations endpoints ----------
@app.get("/healthz")
def healthz():
    """Liveness: the process is up. Never checks the database."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz(response: Response):
    """Readiness: the app can do real work, i.e. the database answers."""
    if store.is_ready():
        return {"status": "ready"}
    response.status_code = 503
    log.warning("readiness check failed", extra={"extra_fields": {"dependency": "database"}})
    return {"status": "not ready", "dependency": "database"}


@app.get("/version")
def version():
    return {"version": APP_VERSION}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------- Business endpoints ----------
class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    priority: Literal["low", "medium", "high"] = "medium"


@app.post("/tasks", status_code=201)
def create_task(task: TaskIn):
    return store.create_task(task.title, task.priority)


@app.get("/tasks")
def list_tasks():
    return store.list_tasks()


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task
