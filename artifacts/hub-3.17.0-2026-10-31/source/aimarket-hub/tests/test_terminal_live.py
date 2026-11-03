"""Network failures must not leave a frozen live feed looking connected."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_terminal_live_network_recovery():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the terminal JavaScript regression tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("terminal_live.test.cjs"))],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
