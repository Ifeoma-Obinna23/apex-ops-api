# Security and configuration

## Secrets handling

| Secret | How it is handled |
|---|---|
| Database password | Generated randomly (`openssl rand -hex 16`), stored only in `.env` on the host, file mode `600`. Never typed or displayed. |
| `.env` | Listed in `.gitignore` (verified with `git check-ignore .env`) and `.dockerignore`, so it never reaches GitHub or an image. `.env.example` holds placeholders only. |
| Compose file | References variables (`${POSTGRES_PASSWORD}`); safe to commit. Validated with `docker compose config --quiet` so the resolved password is never printed. |
| CI registry login | Uses the per-run `GITHUB_TOKEN`, which expires when the job ends, piped via `--password-stdin` so it never appears in logs. No long-lived credentials stored in the repo. |
| CI smoke-test database | Its own random password generated during the run, destroyed with `docker compose down -v`. |
| GitHub CLI token on the workstation | `~/.config/gh/hosts.yml`, mode `600`, outside the repository. |

**Known limitations:** `DATABASE_URL` (which contains the password) is an environment variable of the API container, so anyone with Docker access on the host can read it with `docker inspect`. Next step: Docker secrets or a mounted file locally, and AWS Secrets Manager / SSM Parameter Store in the cloud.

## Least privilege

**Container**
- Runs as a dedicated non-root user `app` with no shell or home directory (`docker exec ... whoami` → `app`).
- Application code is owned by root, so the `app` user cannot modify it.
- Compose hardening: `read_only: true` filesystem (only `/tmp` writable), `cap_drop: [ALL]`, `no-new-privileges`.
- Multi-stage build on `python:3.13-slim`: no compilers or pip caches in the final image.

**Network**
- Postgres has no published port; only the API can reach it, over the private `backend` network.
- The API is published on `127.0.0.1:8000` only, not on the LAN.

**CI**
- Workflow default `permissions: contents: read`.
- Only the `build` job gets `packages: write`, and the publish step runs only on `push` events (never on pull requests).
- GHCR package grants Write to this one repository only.

**Gaps (stated honestly)**
- The API connects as the user created by the Postgres image, which is a database superuser. A separate role with only `SELECT/INSERT/UPDATE` on `tasks` would be tighter.
- Membership of the `docker` group is effectively root on the host. On a shared server, access would go through sudo or rootless Docker.
- No authentication on the API (bound to localhost; out of scope).

## Dependency and image scanning

- All Python dependencies pinned to exact versions (`requirements.txt`); CI actions pinned to major versions; Trivy pinned to `0.65.0`; CI runner pinned to `ubuntu-24.04`.
- **Trivy** scans every built image in CI:
  - report step: HIGH and CRITICAL, informational;
  - gate step: **fails the pipeline on any CRITICAL vulnerability that has a fix available** (`--ignore-unfixed`), so publishing is blocked.
- `ruff` lint on every run.
- Input validation (Pydantic) rejects bad input with 422; SQL uses parameters (`%s`), never string concatenation.

**Next steps:** `pip-audit` for Python CVEs, Dependabot for automatic update PRs, pin actions by commit SHA, generate an SBOM and sign images with cosign, gate on HIGH once the base image is clean.

## Cost-aware path to cloud hosting (AWS)

Nothing was deployed to the cloud for this exercise. The image runs unchanged on any of these:

| Stage | Option | Why |
|---|---|---|
| 1. Cheapest | One small EC2 instance (Graviton `t4g`) or Lightsail running this same `compose.yaml`; Postgres in a container on an EBS volume; nightly `pg_dump` to S3 | Same tooling as local, so nothing new to learn. Lowest cost. Single point of failure, acceptable for a pilot. |
| 2. Managed | App Runner or ECS Fargate for the API + RDS PostgreSQL (`db.t4g.micro`, single-AZ) | No servers to patch, automated DB backups. Higher cost; pay for convenience. |
| 3. Production | Multi-AZ RDS, 2+ Fargate tasks behind an ALB, secrets in Secrets Manager | Availability; only when traffic and business need justify it. |

**Cost controls from day one**
- AWS Budgets alert (e.g. at 50% and 80% of a monthly limit).
- **Avoid NAT gateways** (hourly + per-GB charges are a common surprise): use public subnets with tight security groups, or VPC endpoints.
- Tag every resource (`project=apex-ops-api`, `env=...`) for cost reports.
- Short log retention (e.g. 14 days) and an image lifecycle policy in the registry.
- Stop or `terraform destroy` non-production environments when not in use; prefer Graviton instances.
- Infrastructure as code (Terraform) so environments can be recreated rather than left running.
