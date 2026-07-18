"""Tests for the service.

These run in the CI pipeline (Part 3) BEFORE any image is built. If a test
fails, no broken image ever reaches the registry or the cluster — that is the
whole point of "fail fast" in CI.

We use FastAPI's TestClient, which exercises the real app in-process without
needing a running server.
"""

import importlib

from fastapi.testclient import TestClient

import app.main as main


client = TestClient(main.app)


def test_root_returns_expected_shape():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    # Every field the rest of the system relies on must be present.
    for key in ("message", "environment", "version", "git_sha", "served_by"):
        assert key in body


def test_liveness_is_always_alive():
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_version_endpoint():
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"version", "git_sha", "environment"}


def test_readiness_ready_by_default():
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


def test_readiness_reports_503_when_toggled_off(monkeypatch):
    """When READY=false, the pod must report 503 so K8s pulls it from rotation."""
    monkeypatch.setenv("READY", "false")
    # config + main read env at import time, so reload them to pick up the change.
    import app.config as config

    importlib.reload(config)
    importlib.reload(main)
    local_client = TestClient(main.app)

    resp = local_client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready"}

    # Restore default state so later tests are unaffected.
    monkeypatch.delenv("READY", raising=False)
    importlib.reload(config)
    importlib.reload(main)
