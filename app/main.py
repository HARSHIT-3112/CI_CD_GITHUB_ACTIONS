"""The service itself: a small FastAPI HTTP app.

This is the deployment target for the whole pipeline. It is deliberately tiny —
the interesting engineering is in HOW it gets built, shipped, and run, not in
what it does. But it is built the way a real production service would be:

  * structured JSON logging (machine-parseable, what log aggregators expect)
  * SEPARATE liveness and readiness endpoints (see README / config.py)
  * build/version metadata exposed for observability
  * graceful, dependency-free process
"""

from __future__ import annotations

import json
import logging
import socket
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Response, status

from .config import settings


# --------------------------------------------------------------------------- #
# Logging: emit one JSON object per line. Log collectors (Loki, ELK, Cloud
# Logging) parse this trivially, whereas free-form text is a nightmare to query.
# --------------------------------------------------------------------------- #
class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)
    return logging.getLogger("app")


log = _configure_logging()

# The hostname inside a container is the POD NAME in Kubernetes. Returning it
# lets us literally see which pod (and which blue/green color) answered a
# request — a simple but powerful demonstration tool later on.
HOSTNAME = socket.gethostname()

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Modern startup/shutdown hook (replaces the deprecated @on_event).

    Code before `yield` runs on startup; code after runs on graceful shutdown.
    """
    log.info(
        "service starting "
        f"env={settings.environment} version={settings.version} "
        f"sha={settings.git_sha} port={settings.port} host={HOSTNAME}"
    )
    yield
    log.info("service shutting down")


app = FastAPI(
    title="CI/CD Demo Service",
    version=settings.version,
    description="Deployment target for a production-grade CI/CD pipeline.",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict:
    """Main endpoint: greeting plus identifying metadata."""
    return {
        "message": settings.greeting,
        "environment": settings.environment,
        "version": settings.version,
        "git_sha": settings.git_sha,
        "served_by": HOSTNAME,
    }


@app.get("/version")
async def version() -> dict:
    """Build/version metadata — useful for confirming what is actually deployed."""
    return {
        "version": settings.version,
        "git_sha": settings.git_sha,
        "environment": settings.environment,
    }


@app.get("/health/live")
async def liveness() -> dict:
    """Liveness probe.

    Answers only: 'is this process alive and not deadlocked?' It must NOT check
    external dependencies — otherwise a downstream outage would cause Kubernetes
    to needlessly restart every pod. If we can serve this handler at all, we are
    alive.
    """
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness(response: Response) -> dict:
    """Readiness probe.

    Answers: 'should I receive traffic right now?' This is where real services
    check their dependencies (DB, cache, etc.). We expose a simple toggle
    (the READY env var) so we can demonstrate a pod cleanly leaving the
    load-balancer rotation without being restarted.
    """
    if not settings.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready"}
    return {"status": "ready"}


def run() -> None:
    """Entrypoint for `python -m app.main` (used locally and in the container)."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # noqa: S104 - binding all interfaces is correct inside a container
        port=settings.port,
        log_config=None,  # we manage logging ourselves (JSON above)
    )


if __name__ == "__main__":
    run()
