# Evidence

Text files are terminal output captured from my machine and GitHub. Screenshots show the CI runs.

| File | Shows |
|---|---|
| `01-container.txt` | Image build, non-root user, healthy status, JSON logs, anonymous pull of the CI-built image |
| `02-compose-persistence.txt` | Compose stack, secrets kept out of Git, data surviving container deletion |
| `03-release-rollback.txt` | Deploy 1.0.0 → 1.1.0, rollback to 1.0.0, unknown version refused, deploy 1.2.0, `deploy.log` |
| `04-ci-runs.txt` | Green release run, intentional failure blocking the build, a real CI failure investigated and fixed |
| `05-db-outage-drill.txt` | Database outage investigation, the observability gap found, and the verified fix |
| `06-tests.txt` | Lint and test results |
| `ci-green-run.png` | Release run v1.2.0: test and build jobs green |
| `ci-failure-blocked.png` | Run 41110411363: intentional test failure, build job skipped |

Live CI history: https://github.com/Ifeoma-Obinna23/apex-ops-api/actions
