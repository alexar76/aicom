"""live-stream.html renders a feed from whatever hub ``?hub=`` names, so no field is trusted.

The page is served from the hub's own origin (``/widget/``), the origin of /start and the
key pages. ``latency_ms`` and ``source_hub`` used to reach innerHTML raw, which made
``modelmarket.dev/widget/live-stream.html?hub=<attacker>`` a reflected XSS.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JSDOM = ROOT / "alien-monitor/frontend/node_modules/jsdom"
HELPER = Path(__file__).parent / "js" / "live_stream_xss.cjs"
PAGE = ROOT / "aimarket-widget/live-stream.html"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not JSDOM.exists(),
    reason="needs node and jsdom (alien-monitor/frontend: npm ci)",
)


def test_hostile_feed_inserts_no_markup():
    out = subprocess.run(
        [shutil.which("node"), str(HELPER), str(PAGE)],
        capture_output=True, text=True, timeout=60, check=True,
        env={**os.environ, "JSDOM_PATH": str(JSDOM)},
    )
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result == {"injected_img_tags": 0, "pwned": False}
