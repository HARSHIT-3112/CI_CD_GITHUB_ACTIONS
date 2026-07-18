# Production-Grade CI/CD & Infrastructure Pipeline

An end-to-end, automated path from `git push` to a running, zero-downtime
deployment — built incrementally as a learning + portfolio project.

> **Status:** work in progress. Built one part at a time; each part is
> independently runnable.

## Roadmap

| Part | Topic | Status |
|------|-------|--------|
| 1 | Application (FastAPI service, health/readiness, 12-factor config) | ✅ done |
| 2 | Multi-stage Dockerfile (small, non-root, secure image) | ⬜ |
| 3 | GitHub Actions CI (lint → test → build → scan → push) | ⬜ |
| 4 | Kubernetes manifests (Deployment, Service, probes) | ⬜ |
| 5 | Helm chart | ⬜ |
| 6 | Blue-green deployment | ⬜ |
| 7 | Terraform (IaC) | ⬜ |
| 8 | Vault (secrets management) | ⬜ |
| 9 | Docs & runbook | ⬜ |

## Part 1 — The application

A small [FastAPI](https://fastapi.tiangolo.com/) service that acts as the
deployment target for the pipeline. It is intentionally minimal, but built the
way a production service should be.

### Endpoints

| Method & path      | Purpose |
|--------------------|---------|
| `GET /`            | Greeting + version + `served_by` (pod/host name) |
| `GET /version`     | Build metadata (version, git SHA) |
| `GET /health/live` | **Liveness** — "am I alive?" Never checks dependencies. Failure ⇒ K8s restarts the pod. |
| `GET /health/ready`| **Readiness** — "should I get traffic?" Failure ⇒ K8s removes pod from rotation (no restart). |

### Configuration (all via environment variables — 12-factor)

| Env var       | Default                          | Meaning |
|---------------|----------------------------------|---------|
| `PORT`        | `8000`                           | HTTP listen port |
| `LOG_LEVEL`   | `INFO`                           | Log verbosity |
| `APP_ENV`     | `local`                          | Environment name |
| `APP_VERSION` | `0.0.0-dev`                      | Release version (injected at build) |
| `GIT_SHA`     | `unknown`                        | Source commit (injected at build) |
| `READY`       | `true`                           | Readiness toggle (set `false` to demo rotation removal) |
| `GREETING`    | `Hello from the CI/CD pipeline`  | Sample value (later sourced from Vault) |

### Run it locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements-dev.txt

# lint + test
ruff check app/
pytest app/tests/

# run the server (port 8080 to avoid clashes)
PORT=8080 python -m app.main
curl localhost:8080/
```
