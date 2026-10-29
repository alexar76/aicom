"""A disclosed Mesh credential cannot be restored, including in demo mode."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture
def mesh(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'ai-service-mesh' / 'backend'))
    from ai_service_mesh import security
    return security


@pytest.mark.parametrize('environment', ['development', 'production'])
@pytest.mark.parametrize('override', [False, True])
@pytest.mark.parametrize('role', ['api', 'admin'])
def test_publicly_exposed_identity_cannot_be_reenabled(mesh, monkeypatch, environment, override, role):
    canary = 'synthetic-public-mesh-credential'
    monkeypatch.setattr(mesh, 'COMPROMISED_TOKEN_SHA256', {hashlib.sha256(canary.encode()).hexdigest()})
    keys = {'api_token': 'fresh-api', 'admin_token': 'fresh-admin'}
    keys[role + '_token'] = canary
    with pytest.raises(RuntimeError) as error:
        mesh.assert_production_tokens(environment, **keys, allow_insecure_tokens=override)
    assert canary not in str(error.value)


def test_request_auth_fails_closed_even_without_startup_guard(mesh, monkeypatch):
    from fastapi import HTTPException
    canary = 'synthetic-compromised-runtime-token'
    monkeypatch.setattr(mesh, 'COMPROMISED_TOKEN_SHA256', {hashlib.sha256(canary.encode()).hexdigest()})
    with pytest.raises(HTTPException) as error:
        mesh.require_bearer('Bearer ' + canary, canary, disabled_detail='admin unavailable')
    assert error.value.status_code == 503
    assert canary not in str(error.value)
    mesh.require_bearer('Bearer fresh-admin', 'fresh-admin', disabled_detail='admin unavailable')
    with pytest.raises(HTTPException) as error:
        mesh.require_bearer('Bearer wrong', 'fresh-admin', disabled_detail='admin unavailable')
    assert error.value.status_code == 403


def test_lottery_refuses_to_load_disclosed_outbound_credential(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'lottery' / 'relayer'))
    from ailottery_relayer import config
    canary = 'synthetic-exposed-lottery-token'
    monkeypatch.setattr(config, 'COMPROMISED_MESH_TOKEN_SHA256', {hashlib.sha256(canary.encode()).hexdigest()})
    monkeypatch.setenv('MESH_ADMIN_TOKEN', canary)
    monkeypatch.setenv('LOTTERY_MODE', 'demo')
    with pytest.raises(ValueError) as error:
        config.Config.from_env()
    assert canary not in str(error.value)
    config._guard_mesh_admin_token('fresh-mesh-credential')
