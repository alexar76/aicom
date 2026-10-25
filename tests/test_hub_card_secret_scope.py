"""Shared service environment -> real hub Stripe secret reader, with no network."""

from __future__ import annotations

import pytest
from aimarket_hub import card_topup

from scripts.security.service_env import filtered

pytestmark = pytest.mark.component_integration


@pytest.fixture(params=[
    ("STRIPE_SECRET_KEY", card_topup.secret_key),
    ("STRIPE_WEBHOOK_SECRET", card_topup.webhook_secret),
], ids=["api-key", "webhook"])
def secret_reader(request, monkeypatch):
    name, read = request.param
    for variable in (name, f"{name}_FILE", f"AIMARKET_{name}", f"AIMARKET_{name}_FILE"):
        monkeypatch.delenv(variable, raising=False)
    return name, read


def test_only_the_hubs_scoped_credential_crosses_the_service_boundary(secret_reader, monkeypatch):
    name, read = secret_reader
    entries = filtered("hub", [
        f"{name}=factory-merchant-test-value",
        f"AIMARKET_{name}=hub-merchant-test-value",
    ])
    assert entries == [f"AIMARKET_{name}=hub-merchant-test-value"]
    for entry in entries:
        variable, value = entry.split("=", 1)
        monkeypatch.setenv(variable, value)
    assert read() == "hub-merchant-test-value"


def test_standalone_legacy_configuration_still_works(secret_reader, monkeypatch):
    name, read = secret_reader
    monkeypatch.setenv(name, "legacy-test-value")
    assert read() == "legacy-test-value"


@pytest.mark.parametrize("mode", ["empty", "missing-file", "file"])
def test_explicit_scoped_configuration_never_falls_back_to_another_merchant(
    secret_reader, monkeypatch, tmp_path, mode,
):
    name, read = secret_reader
    monkeypatch.setenv(name, "different-merchant-test-value")
    scoped = f"AIMARKET_{name}"
    expected = ""
    if mode == "empty":
        monkeypatch.setenv(scoped, "")
    else:
        path = tmp_path / "hub-secret"
        if mode == "file":
            path.write_text("scoped-file-test-value\n", encoding="utf-8")
            expected = "scoped-file-test-value"
        monkeypatch.setenv(f"{scoped}_FILE", str(path))
    assert read() == expected
