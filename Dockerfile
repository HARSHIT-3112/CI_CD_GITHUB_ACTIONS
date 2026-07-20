# Multi-stage build for the FastAPI service.
#
#   Stage 1 (builder): has pip + build tooling; installs dependencies into an
#                      isolated virtualenv at /opt/venv.
#   Stage 2 (runtime): slim base with NO build tooling; copies in just the venv
#                      and the app code, and runs as a non-root user.
#
# Only stage 2 is shipped. Everything in stage 1 is thrown away, so the final
# image is small and has a minimal attack surface.

# ----------------------------------------------------------------------------- #
# Stage 1: builder
# ----------------------------------------------------------------------------- #
# Pinned to a specific patch tag for reproducibility. (For maximum supply-chain
# hardening you would pin by sha256 digest; a tag is the readable middle ground.)
FROM python:3.12.8-slim-bookworm AS builder

# PYTHONDONTWRITEBYTECODE: don't litter .pyc files; PYTHONUNBUFFERED: flush logs
# immediately so container stdout is real-time. PIP_NO_CACHE_DIR: no pip cache
# bloating layers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Create an isolated virtualenv we can copy wholesale into the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy ONLY requirements first. This layer is cached and only re-runs when the
# dependency list changes — not when application code changes.
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------------------- #
# Stage 2: runtime
# ----------------------------------------------------------------------------- #
FROM python:3.12.8-slim-bookworm AS runtime

# Build metadata, injected by CI at build time (Part 3). Defaults keep local
# builds working without extra flags.
ARG APP_VERSION=0.0.0-dev
ARG GIT_SHA=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA}

# Apply the latest OS security patches. A pinned base image freezes its Debian
# packages in time; this pulls current security fixes so the scanner's
# "fixable HIGH/CRITICAL" gate (Part 3 CI) stays green. Clean apt lists after to
# keep the layer small. Still done as root, before we drop privileges.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create an unprivileged system user/group. The container will run as this user,
# never as root.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

# Bring in the ready-built virtualenv from the builder stage (no pip/build tools
# come with it) and then the application source.
COPY --from=builder /opt/venv /opt/venv
COPY app/ ./app/

# Drop privileges: everything below and at runtime executes as 'app'.
USER app

EXPOSE 8000

# Docker-level health probe. Uses only the Python stdlib (the slim image has no
# curl). Reads PORT so it stays correct if the port is overridden.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8000')+'/health/live').status==200 else 1)"]

# Exec form (JSON array) so signals (SIGTERM on `kubectl delete`/rollout) reach
# the Python process directly, enabling graceful shutdown.
CMD ["python", "-m", "app.main"]
