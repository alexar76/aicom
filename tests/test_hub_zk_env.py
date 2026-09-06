"""deploy/hub-zk.env.example must enable real PLONK on modelmarket.dev."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZK_ENV = ROOT / "deploy" / "hub-zk.env.example"


def _assignments(key: str) -> list[str]:
    text = ZK_ENV.read_text(encoding="utf-8")
    return re.findall(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)


def test_hub_zk_env_enables_plonk():
    assert ZK_ENV.is_file(), f"missing {ZK_ENV}"
    assert _assignments("AIMARKET_ZK_BACKEND")[-1].strip().lower() == "plonk"
    assert _assignments("AIMARKET_ZK_SIMULATED")[-1].strip() == "0"


def test_hub_zk_env_points_at_image_paths():
    wasm = _assignments("AIMARKET_ZK_WASM")[-1].strip()
    zkey = _assignments("AIMARKET_ZK_ZKEY")[-1].strip()
    vkey = _assignments("AIMARKET_ZK_VKEY_JSON")[-1].strip()
    assert wasm.startswith("/app/contracts/zk/")
    assert zkey.startswith("/app/contracts/zk/")
    assert vkey.startswith("/app/contracts/zk/")
