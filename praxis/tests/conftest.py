"""Keep the practice target's signing key out of `/data` while testing.

PRAXIS defaults `PRAXIS_KEY_PATH` to `/data/praxis_signing_key` — right inside the
container, unwritable everywhere else. The deploy gate runs these tests against a
candidate image, so nobody noticed that on a laptop they could not even be
collected: building a `Signer` creates the key file and its parent directory.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _praxis_key_in_tmp(tmp_path_factory, monkeypatch):
    key = tmp_path_factory.mktemp("praxis-key") / "praxis_signing_key"
    monkeypatch.setenv("PRAXIS_KEY_PATH", str(key))
    import praxis.praxis as mod

    monkeypatch.setattr(mod, "_SIGNER", None, raising=False)
    monkeypatch.setattr(mod, "_KEY_PATH", str(key), raising=False)
    yield
    assert os.environ["PRAXIS_KEY_PATH"] == str(key)
