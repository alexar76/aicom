"""Historical leaked plaintext is never needed by the regression suite."""
import hashlib

import pytest

from security import compromised_credentials as credentials


@pytest.fixture
def compromised_canary(monkeypatch):
    canary = "public-disposable-credential-used-only-in-this-test"
    monkeypatch.setattr(credentials, "COMPROMISED_SHA256", frozenset({hashlib.sha256(canary.encode()).hexdigest()}))
    return canary


def test_rejects_by_fingerprint_without_echoing_value(compromised_canary):
    for value in (compromised_canary, " " + compromised_canary + "\n"):
        with pytest.raises(ValueError) as exc:
            credentials.reject_compromised_credential(value)
        assert compromised_canary not in str(exc.value)
    credentials.reject_compromised_credential(None)
    credentials.reject_compromised_credential("")
    credentials.reject_compromised_credential("different-disposable-credential")


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("environment", [False, True])
def test_provider_refuses_before_constructing_http_transport(provider, environment, compromised_canary, monkeypatch):
    from llm.anthropic_provider import AnthropicProvider
    from llm.openai_compatible import OpenAICompatibleProvider
    import httpx

    def forbidden(*args, **kwargs):
        pytest.fail("a compromised credential reached HTTP transport construction")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setenv("AUDIT_FAKE_PROVIDER_KEY", compromised_canary)
    constructor = OpenAICompatibleProvider if provider == "openai" else AnthropicProvider
    source = {"api_key_env": "AUDIT_FAKE_PROVIDER_KEY"} if environment else {"api_key": compromised_canary}
    with pytest.raises(ValueError):
        constructor(**source)


def test_admin_probe_resolver_also_refuses_direct_and_environment_keys(compromised_canary, monkeypatch):
    from web.backend.api.admin.dashboard.routes_providers import _provider_models_probe, _resolve_provider_api_key

    monkeypatch.setenv("AUDIT_FAKE_PROVIDER_KEY", compromised_canary)
    for conf in ({"api_key": compromised_canary}, {"api_key_env": "AUDIT_FAKE_PROVIDER_KEY"}):
        with pytest.raises(ValueError):
            _resolve_provider_api_key(conf)
    with pytest.raises(ValueError):
        _provider_models_probe(base_url="https://provider.example", health_path="/v1/models", api_key=compromised_canary)
