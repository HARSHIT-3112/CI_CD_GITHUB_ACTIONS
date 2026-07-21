"""Application configuration.

Everything configurable lives here and is read from environment variables
(the 12-factor "config" principle). This is what lets the SAME container image
behave differently in dev, staging, and prod, and lets Helm/Vault inject values
at deploy time without ever rebuilding the image.

Nothing here is hardcoded to a specific environment; every value has a sane
default so the app also runs bare on a laptop with zero setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    """Parse a boolean env var. Accepts 1/true/yes/on (case-insensitive)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _secret_or_env(file_env: str, value_env: str, default: str) -> str:
    """Resolve a value with this precedence:

    1. The contents of the file named by `file_env`, if that env var is set and
       the file exists. This is how a SECRET is consumed: Vault's agent injects
       it into a memory-backed file (e.g. /vault/secrets/greeting) and the app
       reads it here — the value never lives in git, the image, or a ConfigMap.
    2. Otherwise the plain env var `value_env` (non-secret / local dev).
    3. Otherwise the hardcoded default.
    """
    path = os.getenv(file_env)
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass  # fall through if the file isn't there yet
    return os.getenv(value_env, default)


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of configuration, loaded once at startup."""

    # Which port the HTTP server listens on. K8s/Helm can override this.
    port: int = int(os.getenv("PORT", "8000"))

    # Log verbosity. In prod you typically run at INFO; DEBUG locally.
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # A human-friendly name for the environment, surfaced in responses/logs.
    environment: str = os.getenv("APP_ENV", "local")

    # Build metadata. These get injected at image-build time (Part 2) so a
    # running container can tell you exactly which commit it came from.
    version: str = os.getenv("APP_VERSION", "0.0.0-dev")
    git_sha: str = os.getenv("GIT_SHA", "unknown")

    # Readiness toggle. Lets us DEMONSTRATE a pod dropping out of the
    # load-balancer rotation without crashing, which is invaluable for
    # understanding readiness probes and blue-green cutover.
    ready: bool = _get_bool("READY", True)

    # The greeting is our stand-in for a SECRET. In production it is delivered by
    # Vault as a file (GREETING_FILE, e.g. /vault/secrets/greeting); locally it
    # falls back to the GREETING env var, then a default. See _secret_or_env.
    greeting: str = _secret_or_env(
        "GREETING_FILE", "GREETING", "Hello from the CI/CD pipeline"
    )

    # Which blue-green "color" track this instance belongs to (Part 6). Injected
    # by the Deployment. Surfaced in responses so a cutover is visible.
    color: str = os.getenv("COLOR", "none")


# A single shared instance the rest of the app imports.
settings = Settings()
