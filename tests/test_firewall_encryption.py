"""Firewall rules file encryption (Fernet at rest)."""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from security.firewall import FirewallManager


def test_encrypted_roundtrip(tmp_path) -> None:
    key = Fernet.generate_key().decode()
    rules_file = tmp_path / "config" / "firewall_rules.json"
    rules_file.parent.mkdir(parents=True, exist_ok=True)

    fw = FirewallManager(str(rules_file), fernet_key=key)
    fw.clear_rules()
    fw.whitelist_ip("10.88.88.1", "encrypted test")

    raw = json.loads(rules_file.read_text(encoding="utf-8"))
    assert raw.get("aicom_encrypted") is True
    assert isinstance(raw.get("payload"), str)

    fw2 = FirewallManager(str(rules_file), fernet_key=key)
    ok, _reason = fw2.is_allowed("10.88.88.1", 8080)
    assert ok
