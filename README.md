# Production-Grade CI/CD & Infrastructure Pipeline

An end-to-end, automated path from `git push` to a running, zero-downtime
deployment — built incrementally as a learning + portfolio project.

> **Status:** all 9 parts complete. Each part is independently runnable and
> documented below with its own "lessons learned".

## The pipeline at a glance

```
   git push
      │
      ▼
 ┌─────────────────────── GitHub Actions (CI/CD) ───────────────────────┐
 │  test ──► build-scan-push ──────────────────► deploy                 │
 │  ruff    multi-stage Docker build             kind cluster in CI     │
 │  pytest  Trivy scan (fixable HIGH/CRITICAL)   helm upgrade --install │
 │          push image to GHCR                   smoke test the Service │
 └──────────────────────────────────────────────────────────────────────┘
      │  same Helm chart, same image
      ▼
 ┌──────────────────────── Kubernetes (kind) ───────────────────────────┐
 │  Terraform ─► Namespace + Helm release                               │
 │  Helm chart ─► blue / green Deployments  ◄─ Service selector flip     │
 │  Vault Agent ─► injects secrets at runtime (never in git/image/CM)    │
 └──────────────────────────────────────────────────────────────────────┘
```

## Roadmap

| Part | Topic | Status |
|------|-------|--------|
| 1 | Application (FastAPI service, health/readiness, 12-factor config) | ✅ done |
| 2 | Multi-stage Dockerfile (small, non-root, secure image) | ✅ done |
| 3 | GitHub Actions CI (lint → test → build → scan → push) | ✅ done |
| 4 | Kubernetes manifests (Deployment, Service, probes) | ✅ done |
| 5 | Helm chart | ✅ done |
| 6 | Blue-green deployment | ✅ done |
| 7 | Terraform (IaC) | ✅ done |
| 8 | Vault (secrets management) | ✅ done |
| 9 | Continuous Deployment (deploy + smoke test in CI) | ✅ done |

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

## Part 3 — GitHub Actions CI

`.github/workflows/ci.yml` runs on every push/PR to `main`:

```
push / PR ─► test ──────────────► build-scan-push  (needs: test)
             • ruff lint            • buildx build (injects GIT_SHA/APP_VERSION)
             • pytest               • Trivy scan (fail on FIXABLE HIGH/CRITICAL)
                                    • push to GHCR   (main only; PRs skip push)
```

Design choices:

- **Fail-fast gate:** `build-scan-push` declares `needs: test`, so a lint/test
  failure blocks the build entirely.
- **Security gate:** Trivy runs with `--ignore-unfixed --severity HIGH,CRITICAL
  --exit-code 1`. Unpatchable base CVEs are ignored; any *fixable* HIGH/CRITICAL
  fails the build. The image build applies `apt-get upgrade` so this stays green.
- **No secrets:** publishes to **GHCR** using the built-in `GITHUB_TOKEN`
  (`permissions: packages: write`) — no Docker Hub account or PAT.
- **PRs build + scan but don't publish** (`if: github.event_name != 'pull_request'`).
- Trivy is run via its **CLI** (install script), not the wrapper action, to avoid
  a broken transitive pin and keep the command identical to local runs.

Published image: `ghcr.io/<owner-lowercased>/cicd-demo` — tags `latest` (main) and
`sha-<commit>`.

> **Lessons learned (real failures we hit and fixed):**
> 1. A non-existent action tag (`trivy-action@0.28.0`) fails at *"Set up job"* —
>    GitHub resolves all `uses:` before running steps.
> 2. Registry names must be **lowercase**; the owner had uppercase, so the image
>    ref is computed in shell (`${OWNER,,}`) — GitHub expressions have no
>    `lowercase()`.
> 3. CI builds **linux/amd64** (runner arch); pulling on Apple Silicon needs
>    `--platform linux/amd64`, or add a multi-arch buildx build later.

## Part 4 — Kubernetes on a local `kind` cluster

Raw manifests in `k8s/` (numeric-prefixed so `kubectl apply -f k8s/` runs them
in dependency order):

| File | Object | Notes |
|------|--------|-------|
| `00-namespace.yaml` | Namespace | Isolated `cicd-demo` namespace |
| `10-configmap.yaml` | ConfigMap | Non-secret env (`APP_ENV`, `LOG_LEVEL`, `GREETING`) |
| `20-deployment.yaml` | Deployment | 2 replicas, **liveness→`/health/live`**, **readiness→`/health/ready`**, resource requests/limits, hardened `securityContext` |
| `30-service.yaml` | Service | ClusterIP load-balancing across ready pods |

### Run it on kind

```bash
kind create cluster --name cicd

# build + load the image straight into kind (no registry needed locally)
docker build --build-arg APP_VERSION=1.0.3 \
  --build-arg GIT_SHA="$(git rev-parse --short HEAD)" -t cicd-demo:1.0.3 .
kind load docker-image cicd-demo:1.0.3 --name cicd

kubectl apply -f k8s/
kubectl -n cicd-demo rollout status deploy/cicd-demo

# reach it: port-forward the Service (note: this tunnels to ONE pod)
kubectl -n cicd-demo port-forward svc/cicd-demo 8085:80
curl localhost:8085/

# see REAL load-balancing (kube-proxy) from inside the cluster:
kubectl run -n cicd-demo lb-test --image=cicd-demo:1.0.3 \
  --image-pull-policy=IfNotPresent --restart=Never --attach --rm --quiet \
  --command -- python -c "import urllib.request,json; \
print([json.load(urllib.request.urlopen('http://cicd-demo/'))['served_by'] for _ in range(10)])"

# tear down
kind delete cluster --name cicd
```

> **Lessons learned:**
> 1. `kubectl apply -f <dir>` runs files **alphabetically** — the namespace must
>    sort first, hence numeric prefixes (`00-`, `10-`, ...).
> 2. `runAsNonRoot: true` needs a **numeric** UID. A username (`app`) is
>    unverifiable → `CreateContainerConfigError`. Fixed by `USER 10001` in the
>    image + `runAsUser: 10001` in the manifest.
> 3. `kubectl port-forward svc/...` forwards to a **single** pod, not through the
>    load balancer — test load-balancing from inside the cluster instead.
> 4. Local dev loads the image with `kind load` (bypasses registry + arch/auth);
>    a real cluster pulls from GHCR with an `imagePullSecret`.

## Part 5 — Helm chart

`helm/cicd-demo/` packages the Part 4 manifests as a reusable, parameterized
chart. Every hardcoded value now lives in `values.yaml` and is overridable per
environment.

```
helm/cicd-demo/
├── Chart.yaml          # version (chart) + appVersion (app/image)
├── values.yaml         # all the knobs (replicas, image, config, resources, probes, security)
└── templates/
    ├── _helpers.tpl    # name/label helpers (DRY)
    ├── configmap.yaml  # renders .Values.config into env
    ├── deployment.yaml # checksum/config annotation auto-rolls pods on config change
    ├── service.yaml
    └── NOTES.txt       # post-install instructions
```

### Deploy with Helm

```bash
# render/validate without touching the cluster
helm lint ./helm/cicd-demo
helm template cicd-demo ./helm/cicd-demo --set image.tag=1.0.3

# install or upgrade (idempotent) — creates the namespace
helm upgrade --install cicd-demo ./helm/cicd-demo \
  --namespace cicd-demo --create-namespace \
  --set image.tag=1.0.3 --wait

# change any value -> new revision, pods roll automatically
helm upgrade cicd-demo ./helm/cicd-demo -n cicd-demo \
  --set image.tag=1.0.3 --set config.GREETING="Hello from Helm — upgraded!" --wait

# instant rollback + audit trail
helm -n cicd-demo rollback cicd-demo 1
helm -n cicd-demo history cicd-demo
```

> **Why this matters:** the *same chart* deploys any version to any environment
> with different `--set`/`-f` values. Revisions give a full audit trail and
> one-command rollback. This chart becomes the deploy unit for CD (Part 6).

## Part 6 — Blue-green deployment

The chart renders **one Deployment per enabled color** (`blue`/`green`), each
labelled `color: <c>`. The main Service selects `activeColor`; a preview Service
selects `previewColor`. Cutover is an atomic Service-selector flip — no restarts.

```
        main Service (color=blue) ──100%──► ┌──────────┐
                                            │  BLUE    │ v1.0.3  (live)
   preview Service (color=green) ──test──►  ┌──────────┐
                                            │  GREEN   │ v1.0.4  (idle, verifiable)
        flip activeColor=green  ──────────► GREEN goes live; BLUE stays idle for rollback
```

### The blue-green flow

```bash
# 1. blue is live
helm upgrade --install cicd-demo ./helm/cicd-demo -n cicd-demo \
  --set activeColor=blue --set colors.blue.tag=1.0.3 --wait

# 2. deploy green (new version) ALONGSIDE, traffic stays on blue
helm upgrade cicd-demo ./helm/cicd-demo -n cicd-demo \
  --set activeColor=blue \
  --set colors.blue.tag=1.0.3 \
  --set colors.green.enabled=true --set colors.green.tag=1.0.4 \
  --set previewColor=green --wait

# test green privately via the preview Service before any user sees it
kubectl -n cicd-demo run t --image=cicd-demo:1.0.4 --restart=Never -i --rm --quiet \
  --command -- python -c "import urllib.request;print(urllib.request.urlopen('http://cicd-demo-preview/').read())"

# 3. cutover: flip the selector (instant)
helm upgrade cicd-demo ./helm/cicd-demo -n cicd-demo --reuse-values --set activeColor=green --wait

# 4. rollback if needed: flip back (blue never left)
helm upgrade cicd-demo ./helm/cicd-demo -n cicd-demo --reuse-values --set activeColor=blue --wait
```

> **Lessons learned:**
> - Cutover is near-instant but not perfectly atomic per-connection — there's a
>   sub-second EndpointSlice propagation window. Production adds connection
>   draining / readiness gates.
> - Blue-green needs ~2× resources during overlap (both colors run). After a
>   confident cutover you scale down / disable the old color.
> - `color` is excluded from **selector** labels but present on pods, so one
>   Service can target a specific color while the Deployment/pods share the app
>   identity labels.

## Part 7 — Terraform (Infrastructure as Code)

`terraform/` manages the app environment declaratively: a `kubernetes_namespace`
plus a `helm_release` of our chart, via the `kubernetes` and `helm` providers.
The kind cluster stands in for cloud infra — in AWS/GCP a cluster module (EKS/GKE)
would be added here and the providers pointed at its outputs.

```
terraform/
├── versions.tf     # pinned Terraform + provider versions
├── providers.tf    # kubernetes + helm, targeting the kind-cicd context
├── main.tf         # kubernetes_namespace + helm_release
├── variables.tf    # image tags, replicas, blue-green active_color (validated)
├── outputs.tf      # namespace, release, status
└── terraform.tfvars.example
```

### Usage

```bash
cd terraform
terraform init
terraform plan                              # preview the diff
terraform apply                             # build the whole env from code
terraform apply -var active_color=green     # blue-green cutover, as code
terraform output                            # namespace/release/status
terraform destroy                           # tear it all down
```

> **Lessons learned:**
> - `terraform` is no longer in homebrew-core (BSL license) — install from
>   `hashicorp/tap`.
> - Terraform only manages what it created; the manually-installed Helm release
>   had to be removed first so Terraform could own it (alternative: `terraform import`).
> - Commit `.terraform.lock.hcl` (pins provider versions); **gitignore** state
>   (`*.tfstate`) and real `*.tfvars` (they can hold secrets).
> - Driving Helm through Terraform means one `plan`/`apply`/`destroy` covers
>   infra **and** app together.

## Part 8 — Vault (secrets management)

Secrets must never live in git, images, ConfigMaps, or manifest env vars. Vault
stores them once (encrypted, audited) and delivers them to pods **at runtime**,
authenticated by the pod's **ServiceAccount identity** — no static password.

We use the **Vault Agent Injector**: pod annotations add an init container that
authenticates to Vault, reads the secret, and renders it to a memory-backed file
`/vault/secrets/greeting`. The app reads that file (`GREETING_FILE`).

```
pod (SA: cicd-demo) ─► injector adds vault-agent-init
   init authenticates via Kubernetes auth ─► Vault checks role/policy ─► allowed
   secret rendered to /vault/secrets/greeting (tmpfs) ─► app reads it at startup
```

### Set it up (dev-mode Vault on kind)

```bash
helm repo add hashicorp https://helm.releases.hashicorp.com
helm install vault hashicorp/vault -n vault --create-namespace \
  --set server.dev.enabled=true --set server.dev.devRootToken=root

# store the secret + configure k8s auth, policy, and a role bound to the app SA
kubectl -n vault exec vault-0 -- sh -c '
  export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root
  vault kv put secret/cicd-demo greeting="…secret…"
  vault auth enable kubernetes
  vault write auth/kubernetes/config kubernetes_host="https://kubernetes.default.svc:443"
  vault policy write cicd-demo - <<EOF
path "secret/data/cicd-demo" { capabilities = ["read"] }
EOF
  vault write auth/kubernetes/role/cicd-demo \
    bound_service_account_names=cicd-demo \
    bound_service_account_namespaces=cicd-demo policies=cicd-demo ttl=1h'

# deploy with injection on (image >= 1.0.5 reads GREETING_FILE)
cd terraform && terraform apply -var vault_enabled=true -var blue_tag=1.0.5 -var green_tag=1.0.5
```

The secret then appears in the app's response but is absent from the ConfigMap,
the image env, and git.

> **Lessons learned:**
> - The injector template annotation contains Vault's own `{{ }}` — render it via
>   Helm `printf` with a backtick string so Helm doesn't try to interpret it.
> - Vault authorizes by **ServiceAccount**, so the app needs a dedicated SA that
>   the Vault role is bound to (name + namespace must match).
> - Injected pods gain an init container + a `vault-agent` sidecar (pods show 2/2).
> - `server.dev.enabled=true` is for LEARNING ONLY (in-memory, auto-unsealed, root
>   token). Production Vault is HA, persistent, sealed, and audited.

## Part 9 — Continuous Deployment (CD)

The CI workflow gains a third job, `deploy` (`needs: build-scan-push`, main only),
that closes the loop from push to *verified running*:

```
deploy job:
  create ephemeral kind cluster (on the runner)
  ─► pull the GHCR image for this commit, kind-load it
  ─► helm upgrade --install (the SAME chart) with the commit's image tag
  ─► port-forward the Service and smoke-test /health/ready and /
```

The smoke test fails the job if the deployed app doesn't answer 200 with a
well-formed response — a real deployment gate, no cloud account or secrets needed.

> **Targeting a real cluster:** replace the "Create kind cluster" step with one
> that writes a kubeconfig from a secret (`${{ secrets.KUBECONFIG }}`) and drop
> the `kind load` step (a real cluster pulls from GHCR via an `imagePullSecret`).
> Everything else — the Helm release, the values, the smoke test — is identical.

---

## Bring the whole stack up locally

```bash
# 1. cluster
kind create cluster --name cicd

# 2. build + load images
for v in 1.0.3 1.0.4 1.0.5; do
  docker build --build-arg APP_VERSION=$v \
    --build-arg GIT_SHA="$(git rev-parse --short HEAD)" -t cicd-demo:$v .
  kind load docker-image cicd-demo:$v --name cicd
done

# 3. Vault (dev) + configure (see Part 8 for the exec block)
helm repo add hashicorp https://helm.releases.hashicorp.com
helm install vault hashicorp/vault -n vault --create-namespace \
  --set server.dev.enabled=true --set server.dev.devRootToken=root

# 4. deploy everything via Terraform
cd terraform && terraform init && \
  terraform apply -auto-approve -var vault_enabled=true -var blue_tag=1.0.5 -var green_tag=1.0.5

# teardown
terraform destroy -auto-approve
kind delete cluster --name cicd
```
