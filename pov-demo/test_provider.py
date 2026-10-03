"""The two demo providers: the honest one is right, the cheat is wrong, both sign validly."""
import base64
import importlib
import json
import math
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv("POV_DEMO_KEY_DIR", str(tmp_path))
    monkeypatch.setenv("POV_DEMO_PERSONAS", "honest,cheat")
    sys.path.insert(0, str(Path(__file__).parent))
    sys.modules.pop("provider", None)
    return importlib.import_module("provider")


def test_honest_is_right_and_cheat_is_wrong(provider):
    for n in (1000009, 8051, 600851475143, 97):
        honest = provider.deliver("honest", n)["factors"]
        cheat = provider.deliver("cheat", n)["factors"]
        assert math.prod(honest) == n
        assert math.prod(cheat) != n


def test_both_sign_validly_with_different_keys(provider):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    assert provider.pubkey("honest") != provider.pubkey("cheat")
    payload, result = {"n": 8051}, provider.deliver("cheat", 8051)
    sig = provider.KEYS["cheat"].sign(provider.canonical("math.factor@v1", "quickfactor", payload, result))
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(provider.pubkey("cheat")))
    pub.verify(sig, provider.canonical("math.factor@v1", "quickfactor", payload, result))


def test_keys_are_private_files(provider, tmp_path):
    for name in ("honest", "cheat"):
        assert oct(os.stat(tmp_path / f"{name}.key").st_mode & 0o777) == "0o600"


def test_the_cheat_is_off_unless_asked_for(tmp_path, monkeypatch):
    monkeypatch.setenv("POV_DEMO_KEY_DIR", str(tmp_path))
    monkeypatch.delenv("POV_DEMO_PERSONAS", raising=False)
    sys.path.insert(0, str(Path(__file__).parent))
    sys.modules.pop("provider", None)
    mod = importlib.import_module("provider")
    assert list(mod.PERSONAS) == ["honest"]
