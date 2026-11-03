"""Execute the actual search renderer and submit handler against adversarial responses."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_terminal_search_evidence():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for terminal JavaScript regression tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("terminal_search_evidence.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
