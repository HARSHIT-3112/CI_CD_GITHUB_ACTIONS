# Production-Grade CI/CD & Infrastructure Pipeline

An end-to-end, automated path from `git push` to a running, zero-downtime
deployment — built incrementally as a learning + portfolio project.

> **Status:** work in progress. Built one part at a time; each part is
> independently runnable.

## Roadmap

| Part | Topic | Status |
|------|-------|--------|
| 1 | Application (FastAPI service, health/readiness, 12-factor config) | ✅ done |
| 2 | Multi-stage Dockerfile (small, non-root, secure image) | ✅ done |
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

## Part 2 — Multi-stage Docker image

A two-stage `Dockerfile` builds a small, non-root production image:

- **Stage 1 (builder):** installs dependencies into an isolated virtualenv
  (`/opt/venv`) using pip + build tooling.
- **Stage 2 (runtime):** `python:3.12-slim` base with **no** build tooling —
  copies in just the venv + app code, and runs as an unprivileged `app` user.

Only the runtime stage ships. Design choices: `slim` (glibc) over `alpine`
(musl) for wheel compatibility, non-root user, build-arg injection of
`APP_VERSION`/`GIT_SHA`, a stdlib `HEALTHCHECK`, and a `.dockerignore` that keeps
`.git`/`.venv`/tests/secrets out of the build context.

### Build & run

```bash
# build, injecting version + commit
docker build \
  --build-arg GIT_SHA="$(git rev-parse --short HEAD)" \
  --build-arg APP_VERSION="1.0.1" \
  -t cicd-demo:1.0.1 .

# run it (host 8083 -> container 8000)
docker run -d --name demo -p 8083:8000 cicd-demo:1.0.1
curl localhost:8083/version
docker rm -f demo
```

### Security scanning (Trivy)

```bash
# app dependencies (should be clean; we keep pins current)
trivy image --scanners vuln --severity HIGH,CRITICAL --pkg-types library cicd-demo:1.0.1

# OS base packages (some CVEs are upstream-unfixable; CI gates on FIXABLE only — Part 3)
trivy image --scanners vuln --severity HIGH,CRITICAL --pkg-types os cicd-demo:1.0.1
```

> **Lesson learned:** pinned deps give reproducibility but must be actively
> bumped for security. The initial build flagged 3 HIGH `starlette` CVEs;
> upgrading FastAPI/uvicorn cleared them. Base-image CVEs are handled by regular
> rebuilds + a fixable-only CI gate.
