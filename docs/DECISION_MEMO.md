# Decision memo

**Goal:** a reproducible, reviewable path from commit to release for a small API, run locally, with safe rollback and basic operations.

## Key decisions and trade-offs

| Decision | Why | Trade-off accepted |
|---|---|---|
| **Python + FastAPI**, own minimal API | Small, readable, built-in validation and `/docs`; Python is my scripting language | Not the fastest runtime; irrelevant at this scale |
| **PostgreSQL in Compose** with a named volume | Real dependency to make readiness, persistence and failure drills meaningful | More moving parts than SQLite |
| **Two storage backends** (Postgres, in-memory) behind one interface | Unit tests run in under a second with no database, on any machine | Postgres-specific bugs are caught only by the CI smoke test, not unit tests |
| **Liveness ≠ readiness** | A database outage should not trigger pointless API restarts; readiness names the failing dependency | Two endpoints to maintain |
| **Two CI gates** (`test` then `build`, `needs: test`) | A failing test means no image exists, so nothing can be deployed | Slightly longer pipeline (~1.5 min) |
| **Smoke test of the built image against real Postgres in CI** | Proves the artifact works, not just the source code | Adds ~30 s per run |
| **Trivy gate on fixable CRITICAL only** | Blocks real, actionable risk without blocking on issues no one can fix yet | HIGH findings are reported, not blocking |
| **Versioned images from Git tags** (`v1.2.0` → `:1.2.0`), commit builds as `sha-xxxxxxx` | Every running image traces back to exact code; rollback = choose an older tag | Tags can be moved; digests would be stricter |
| **Deploy only CI-published images** (`docker pull` first) | No "built on my laptop" releases; a typo or untested version cannot go live | Needs registry access to deploy |
| **Bash deploy/rollback scripts with auto-rollback** | Executable, readable, testable with shellcheck; matches a single-host target | Not zero-downtime: a few seconds of unavailability while the API container is replaced |
| **Additive-only schema changes** | Any released version can run on current data, so rollback is safe | Cleanup of old columns needs a later, separate release |
| **Docker Engine inside WSL2 instead of Docker Desktop** | Docker Desktop's WSL bridge hung on my machine and recovered only after a full reboot; native Engine is managed by systemd like a real Linux server | Docker Desktop GUI not used |
| **GHCR, public package** | Free, next to the code; anyone (reviewers, a server) can pull without credentials | Image is public; acceptable because it contains no secrets |

## What happened along the way

- **CI publish failed** (`error from registry: denied`). Logs showed login and layer upload succeeded; the repository lacked write access to the package. Fixed in package and workflow permissions, re-ran only the failed job.
- **Database outage drill exposed an observability gap:** 500 errors were neither logged nor counted in metrics, so the error-rate alert could not fire. Fixed and released as 1.2.0, verified by a second drill. See `docs/OBSERVABILITY.md`.

## Measured results

- CI: ~1.5 min per run; failing tests stop the pipeline in ~15–20 s with the build job skipped.
- Deploy 1.0.0 → 1.2.0: 17 s. Rollback 1.1.0 → 1.0.0: 9 s. No data loss in either direction.

## Risks and what I would do with more time

1. **Zero-downtime deploys:** run two API containers behind a reverse proxy (or move to ECS/Kubernetes rolling updates).
2. **Secrets:** move `DATABASE_URL` to Docker secrets / a secrets manager; least-privileged DB role.
3. **Database migrations:** a migration tool (Alembic) instead of `CREATE TABLE IF NOT EXISTS`.
4. **Deploy script:** label rollbacks explicitly in `deploy.log`, log failed pulls, deploy by image digest, keep a release history file.
5. **Monitoring:** actually run Prometheus + Grafana + Alertmanager via a Compose profile; JSON-format Uvicorn's own log lines.
6. **Supply chain:** pin actions by SHA, `pip-audit`, Dependabot, SBOM and image signing.
7. **Tests:** integration tests against Postgres in the test job; concurrency tests.
8. **API:** authentication and rate limiting before exposing beyond localhost.
