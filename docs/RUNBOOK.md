# Runbook: Apex Operations API

All commands run from the repository folder on the host (`cd ~/apex-ops-api`).

## Quick reference

| I need to... | Command |
|---|---|
| See what is running | `docker compose ps` and `curl -s localhost:8000/version` |
| Deploy a version | `./scripts/deploy.sh 1.2.0` |
| Roll back | `./scripts/rollback.sh` (or `./scripts/rollback.sh 1.0.0`) |
| Read the deploy history | `cat deploy.log` |
| Read API logs | `docker compose logs api --since 10m` |
| Find one request | `docker compose logs api \| grep <request_id>` |
| Check health | `curl -s -w " %{http_code}\n" localhost:8000/readyz` |
| See error counts | `curl -s localhost:8000/metrics \| grep 'status="5'` |

## 1. Deploy

**Before:** the version must have a green CI run and exist in GHCR. Check with `gh run list --workflow=ci.yml --limit 5`.

```bash
./scripts/deploy.sh 1.2.0
```

What the script does:
1. Records the current version from `.env` (`API_TAG`).
2. `docker pull` the new version. If CI never published it, the script stops here and nothing changes.
3. Sets `API_TAG` in `.env` and recreates **only** the `api` container, waiting until it is healthy (60 s limit). The database is not touched.
4. Verifies `/readyz` returns 200 and `/version` reports the new version.
5. On success, saves the old version to `.previous_version`. On failure, switches back to the old version automatically and exits with an error.
6. Logs each step with a UTC timestamp to `deploy.log`.

**After:** `curl -s localhost:8000/version` and `docker compose ps` (api should be `healthy`).

Measured: deploy of 1.2.0 took 17 s (pull + switch + verify).

## 2. Roll back

Use when a newly deployed version misbehaves (errors, wrong behaviour) even though it passed its checks.

```bash
./scripts/rollback.sh            # to the version recorded before the last successful deploy
./scripts/rollback.sh 1.0.0      # or to a specific version
```

Rollback re-uses `deploy.sh`, so it gets the same pull, health wait, verification and logging.

**Verify:** `/version` shows the old version, and a feature only in the newer version returns 404 (e.g. `POST /tasks/1/close` after rolling back from 1.1.0 to 1.0.0).

Measured: rollback from 1.1.0 to 1.0.0 took 9 s; data written by 1.1.0 remained readable.

**Rule that keeps rollback safe:** database changes must be backward-compatible (add columns or tables; never rename or drop in the same release as the code that needs it).

## 3. Incident response

1. **Acknowledge** the alert and note the time.
2. **Scope:** what is broken and who is affected?
   ```bash
   curl -s -w " %{http_code}\n" localhost:8000/healthz   # process alive?
   curl -s -w " %{http_code}\n" localhost:8000/readyz    # dependencies OK?
   docker compose ps                                      # which container is down/unhealthy?
   ```
3. **Find recent change:** `tail -5 deploy.log`. If the problem started right after a deploy, **roll back first, investigate second.**
4. **Read logs:** `docker compose logs api --since 15m | grep -E '"level": "(ERROR|WARNING)"'`
5. **Mitigate:** roll back, or restart/recover the failed dependency.
6. **Verify:** `/readyz` 200, `/metrics` shows no new 5xx.
7. **Write it up:** what happened, impact, root cause, fix, follow-up actions.

### Example: database unavailable (drill performed, see evidence/05)

| Signal | Value |
|---|---|
| `/healthz` | 200 (process fine, so restarting the API would not help) |
| `/readyz` | 503 `{"dependency":"database"}` |
| `/tasks` | 500 with `request_id` in the body |
| Logs | `ERROR unhandled error ... "error_type": "OperationalError", "error": "Name or service not known"` |
| `docker compose ps` | `db` missing from the list |

Root cause: database container stopped. A stopped container is removed from Docker's internal DNS, which is why the error is "Name or service not known" rather than "connection refused".
Fix: `docker compose start db`. Verified with `/readyz` returning 200 and data still present.

## 4. Troubleshooting

| Symptom | Likely cause | Check / fix |
|---|---|---|
| `deploy.sh` fails at `docker pull` with "manifest unknown" | Version never published (CI failed or typo) | `gh run list`; deploy a published version |
| `docker pull` says denied / unauthorized | GHCR package is private | Package settings → visibility Public, or `docker login ghcr.io` |
| CI Publish step: `error from registry: denied` | Repo has no write access to the GHCR package | Package settings → Manage Actions access → add repo with Write; repo Settings → Actions → Workflow permissions → Read and write. Then `gh run rerun <id> --failed` |
| CI test job red, build skipped | A test or lint failed (by design the release is blocked) | `gh run view <id> --log-failed`, fix, push again |
| `/readyz` 503 | Database down or unreachable | `docker compose ps`, `docker compose logs db`, `docker compose start db` |
| api `unhealthy` | App not answering `/healthz` | `docker compose logs api`; roll back if it started after a deploy |
| `docker compose up` error: port 8000 already allocated | Another process on 8000 (e.g. a local uvicorn) | `sudo ss -ltnp \| grep 8000`, stop it |
| `docker` commands hang in WSL; "Cannot connect to the Docker daemon" | Docker Desktop WSL integration broken | Use Docker Engine inside Ubuntu: `sudo apt install docker.io docker-compose-v2`, `sudo systemctl enable --now docker`, add user to `docker` group |
| Permission denied on `/var/run/docker.sock` | User not in `docker` group | `sudo usermod -aG docker $USER`, open a new terminal |
| Compose variables empty / warnings | `.env` missing | `cp .env.example .env` and set a password |

## 5. Routine checks

- After every deploy: `/version`, `/readyz`, `docker compose ps`.
- Weekly: review Trivy output in the latest CI run; rebuild to pick up base-image patches.
- Before risky work: back up the database: `docker compose exec db pg_dump -U apex_app apex_ops > backup.sql` (add `-T` after `exec` if scripting).
