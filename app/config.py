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

    # Example of a value that will later come from Vault (Part 8) instead of
    # a plain env var. For now it is just a harmless string.
    greeting: str = os.getenv("GREETING", "Hello from the CI/CD pipeline")

    # Which blue-green "color" track this instance belongs to (Part 6). Injected
    # by the Deployment. Surfaced in responses so a cutover is visible.
    color: str = os.getenv("COLOR", "none")


# A single shared instance the rest of the app imports.
settings = Settings()
