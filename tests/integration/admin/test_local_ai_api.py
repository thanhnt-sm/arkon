"""
Integration tests for /api/admin/local-ai/* endpoints.

Strategy:
  - No real DB: ConfigService is stubbed via sys.modules injection.
  - No real LM Studio: LMSClient is patched via unittest.mock.
  - Auth: require_permission dependency is overridden on the app.
  - TestClient (sync) wraps the async FastAPI app.

Coverage:
  - GET  /config returns defaults when KV empty
  - POST /config with valid body persists + returns updated
  - POST /config with invalid mode → 422
  - POST /reset-max sets mode=max + writes preset keys
  - GET  /health with no LM Studio → ok=false + error message
  - Unauthenticated → 403 (dependency raises HTTPException)
"""

from __future__ import annotations

import sys
import types
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers — stub out heavy DB / auth / config dependencies
# ---------------------------------------------------------------------------


def _make_kv_backend(initial: Optional[dict] = None) -> tuple[dict, MagicMock]:
    """Create a KV store dict + a ConfigService mock that reads/writes it."""
    store: dict = dict(initial or {})

    async def _get(key: str) -> Optional[str]:
        return store.get(key)

    async def _set(key: str, value: str) -> None:
        store[key] = value

    mock_instance = MagicMock()
    mock_instance.get = AsyncMock(side_effect=_get)
    mock_instance.set = AsyncMock(side_effect=_set)

    mock_cls = MagicMock(return_value=mock_instance)
    return store, mock_cls


def _inject_config_service(mock_cls: MagicMock) -> Optional[types.ModuleType]:
    """Override app.services.config_service in sys.modules."""
    fake_mod = types.ModuleType("app.services.config_service")
    fake_mod.ConfigService = mock_cls  # type: ignore[attr-defined]
    original = sys.modules.get("app.services.config_service")
    sys.modules["app.services.config_service"] = fake_mod
    return original


def _restore_config_service(original: Optional[types.ModuleType]) -> None:
    if original is None:
        sys.modules.pop("app.services.config_service", None)
    else:
        sys.modules["app.services.config_service"] = original


def _make_test_app(kv_mock_cls: MagicMock) -> tuple[FastAPI, TestClient]:
    """
    Build a minimal FastAPI app that includes only the admin_local_ai router
    with auth dependency overridden to allow any request (simulates admin user).

    Strategy: override `get_current_user` — since require_permission._check
    always delegates to it and then short-circuits when role == "admin",
    injecting an admin Employee bypasses all permission checks without needing
    to capture the exact require_permission closure reference.
    """
    from app.database import get_db
    from app.database.models import Employee
    from app.services.auth_service import get_current_user
    from app.routers.admin_local_ai import router

    app = FastAPI()

    # Fake DB session dependency — commit must be awaitable
    fake_db = MagicMock()
    fake_db.commit = AsyncMock()

    async def _fake_db():
        yield fake_db

    # Fake admin user — role="admin" bypasses all permission checks
    fake_user = MagicMock(spec=Employee)
    fake_user.id = "admin-test-id"
    fake_user.role = "admin"

    def _fake_current_user():
        return fake_user

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_current_user

    app.include_router(router, prefix="/api")

    client = TestClient(app, raise_server_exceptions=False)
    return app, client


# ---------------------------------------------------------------------------
# 1. GET /config returns defaults when KV is empty
# ---------------------------------------------------------------------------


def test_get_config_returns_defaults_when_kv_empty():
    store, mock_cls = _make_kv_backend({})
    original = _inject_config_service(mock_cls)
    try:
        _, client = _make_test_app(mock_cls)
        resp = client.get("/api/admin/local-ai/config")
    finally:
        _restore_config_service(original)

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "off"
    assert "lms_host" in data
    assert data["lms_auth_token"] == ""  # empty → masked as ""
    assert "vision" in data
    assert "main_llm" in data
    assert "embedding" in data
    assert "sampling" in data


# ---------------------------------------------------------------------------
# 2. POST /config with valid body persists and returns updated
# ---------------------------------------------------------------------------


def test_post_config_valid_body_persists_and_returns_updated():
    from app.services.audit_service import log_audit

    store, mock_cls = _make_kv_backend({})
    original = _inject_config_service(mock_cls)
    try:
        _, client = _make_test_app(mock_cls)

        with patch("app.routers.admin_local_ai.log_audit", new_callable=AsyncMock):
            with patch("app.routers.admin_local_ai.save_config", new_callable=AsyncMock) as mock_save:
                with patch("app.routers.admin_local_ai.load_config", new_callable=AsyncMock) as mock_load:
                    from app.ai.local_orchestrator.config import LocalAIConfig
                    mock_load.return_value = LocalAIConfig(mode="off")

                    resp = client.post(
                        "/api/admin/local-ai/config",
                        json={
                            "mode": "max",
                            "lms_host": "http://192.168.1.10:1234",
                        },
                    )
    finally:
        _restore_config_service(original)

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "max"
    assert data["lms_host"] == "http://192.168.1.10:1234"


# ---------------------------------------------------------------------------
# 3. POST /config with invalid mode → 422
# ---------------------------------------------------------------------------


def test_post_config_invalid_mode_returns_422():
    store, mock_cls = _make_kv_backend({})
    original = _inject_config_service(mock_cls)
    try:
        _, client = _make_test_app(mock_cls)
        resp = client.post("/api/admin/local-ai/config", json={"mode": "turbo"})
    finally:
        _restore_config_service(original)

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. POST /reset-max sets mode=max and writes MAX_PRESET keys
# ---------------------------------------------------------------------------


def test_post_reset_max_sets_mode_max():
    store, mock_cls = _make_kv_backend({"local_ai.mode": "off"})
    original = _inject_config_service(mock_cls)
    try:
        _, client = _make_test_app(mock_cls)

        with patch("app.routers.admin_local_ai.log_audit", new_callable=AsyncMock):
            with patch("app.routers.admin_local_ai.save_config", new_callable=AsyncMock) as mock_save:
                with patch("app.routers.admin_local_ai.load_config", new_callable=AsyncMock) as mock_load:
                    from app.ai.local_orchestrator.config import LocalAIConfig
                    mock_load.return_value = LocalAIConfig(
                        mode="off",
                        lms_host="http://host.docker.internal:1234",
                        lms_auth_token="",
                    )

                    resp = client.post("/api/admin/local-ai/reset-max")
    finally:
        _restore_config_service(original)

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "max"
    assert mock_save.called
    # Verify the config passed to save_config has mode=max
    saved_config = mock_save.call_args[0][1]
    assert saved_config.mode == "max"


# ---------------------------------------------------------------------------
# 5. GET /health with no LM Studio → ok=false
# ---------------------------------------------------------------------------


def test_get_health_no_lm_studio_returns_ok_false():
    store, mock_cls = _make_kv_backend({})
    original = _inject_config_service(mock_cls)
    try:
        _, client = _make_test_app(mock_cls)

        with patch("app.routers.admin_local_ai.load_config", new_callable=AsyncMock) as mock_load:
            from app.ai.local_orchestrator.config import LocalAIConfig
            mock_load.return_value = LocalAIConfig(mode="off")

            # Patch LMSClient.health to simulate connection refused
            with patch(
                "app.routers.admin_local_ai.LMSClient",
                autospec=False,
            ) as MockLMSClient:
                mock_lms_instance = MagicMock()
                mock_lms_instance.health = AsyncMock(return_value=False)
                mock_lms_instance.list_loaded = AsyncMock(return_value=[])
                MockLMSClient.return_value = mock_lms_instance

                resp = client.get("/api/admin/local-ai/health")
    finally:
        _restore_config_service(original)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "loaded_models" in data


# ---------------------------------------------------------------------------
# 6. GET /health with LM Studio up → ok=true + loaded models
# ---------------------------------------------------------------------------


def test_get_health_lm_studio_up_returns_ok_true():
    store, mock_cls = _make_kv_backend({})
    original = _inject_config_service(mock_cls)
    try:
        _, client = _make_test_app(mock_cls)

        with patch("app.routers.admin_local_ai.load_config", new_callable=AsyncMock) as mock_load:
            from app.ai.local_orchestrator.config import LocalAIConfig
            mock_load.return_value = LocalAIConfig(mode="max")

            with patch("app.routers.admin_local_ai.LMSClient", autospec=False) as MockLMSClient:
                mock_lms_instance = MagicMock()
                mock_lms_instance.health = AsyncMock(return_value=True)
                mock_lms_instance.list_loaded = AsyncMock(
                    return_value=["mlx-community/Qwen2.5-VL-32B-Instruct-4bit"]
                )
                MockLMSClient.return_value = mock_lms_instance

                resp = client.get("/api/admin/local-ai/health")
    finally:
        _restore_config_service(original)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["loaded_models"]) == 1


# ---------------------------------------------------------------------------
# 7. Auth gating — unauthenticated request → 403
# ---------------------------------------------------------------------------


def test_unauthenticated_get_config_returns_401_or_403():
    """Without auth override, get_current_user raises 401/403 (no token)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.routers.admin_local_ai import router
    from app.services.config_service import ConfigService  # type: ignore[import]

    app = FastAPI()

    # Provide a fake DB — commit must be awaitable
    fake_db = MagicMock()
    fake_db.commit = AsyncMock()

    async def _fake_db():
        yield fake_db

    # Leave get_current_user unoverridden so auth fires for real
    app.dependency_overrides[get_db] = _fake_db
    app.include_router(router, prefix="/api")

    client = TestClient(app, raise_server_exceptions=False)
    # No Authorization header → get_current_user → 401
    resp = client.get("/api/admin/local-ai/config")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 8. Auth token write-only: "•••" placeholder → existing token kept
# ---------------------------------------------------------------------------


def test_post_config_auth_token_placeholder_keeps_existing():
    store, mock_cls = _make_kv_backend({})
    original = _inject_config_service(mock_cls)
    try:
        _, client = _make_test_app(mock_cls)

        with patch("app.routers.admin_local_ai.log_audit", new_callable=AsyncMock):
            with patch("app.routers.admin_local_ai.save_config", new_callable=AsyncMock) as mock_save:
                with patch("app.routers.admin_local_ai.load_config", new_callable=AsyncMock) as mock_load:
                    from app.ai.local_orchestrator.config import LocalAIConfig
                    mock_load.return_value = LocalAIConfig(
                        mode="off",
                        lms_auth_token="my-secret-token",
                    )

                    # Sending back the placeholder should NOT overwrite the token
                    resp = client.post(
                        "/api/admin/local-ai/config",
                        json={"lms_auth_token": "•••"},
                    )
    finally:
        _restore_config_service(original)

    assert resp.status_code == 200
    saved_config = mock_save.call_args[0][1]
    assert saved_config.lms_auth_token == "my-secret-token"


# ---------------------------------------------------------------------------
# 9. LocalAIConfig.from_max_preset classmethod
# ---------------------------------------------------------------------------


def test_from_max_preset_returns_mode_max():
    from app.ai.local_orchestrator.config import LocalAIConfig
    from app.ai.local_orchestrator.presets import MAX_PRESET

    cfg = LocalAIConfig.from_max_preset()
    assert cfg.mode == "max"
    assert cfg.vision.model_id == MAX_PRESET["vision"]["model_id"]
    assert cfg.main_llm.context_length == MAX_PRESET["main_llm"]["context_length"]


def test_from_max_preset_preserves_host_and_token():
    from app.ai.local_orchestrator.config import LocalAIConfig

    cfg = LocalAIConfig.from_max_preset(
        preserve_host="http://10.0.0.5:1234",
        preserve_token="tok123",
    )
    assert cfg.mode == "max"
    assert cfg.lms_host == "http://10.0.0.5:1234"
    assert cfg.lms_auth_token == "tok123"
