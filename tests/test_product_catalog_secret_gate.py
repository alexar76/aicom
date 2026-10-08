"""The product-catalog publisher pushes factory-built trees to a public, append-only repo,
so a secret that lands there cannot be taken back. It runs the same scan as the satellite
mirrors on every product tree and refuses to commit when the scan fails.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_factory_product_catalog.sh"

pytestmark = pytest.mark.skipif(
    not (shutil.which("rg") and shutil.which("rsync") and shutil.which("git")),
    reason="needs rg, rsync and git",
)


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _remote(tmp_path: Path) -> Path:
    # The script only accepts an alexar76/aicom-products remote; a local bare repo at a
    # path that spells it is accepted the same way and never reaches the network.
    bare = tmp_path / "github.com" / "alexar76" / "aicom-products.git"
    bare.parent.mkdir(parents=True)
    _git("init", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    _git("init", "-b", "main", str(seed))
    (seed / "README.md").write_text("# aicom-products\n", encoding="utf-8")
    _git("add", "-A", cwd=seed)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed", cwd=seed)
    _git("push", "-q", str(bare), "HEAD:main", cwd=seed)
    return bare


def _product(tmp_path: Path, body: str) -> Path:
    src = tmp_path / "product"
    src.mkdir()
    (src / "README.md").write_text("# demo product\n", encoding="utf-8")
    (src / "app.py").write_text(body, encoding="utf-8")
    return src


def _publish(tmp_path: Path, bare: Path, src: Path) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GH_PAT": "test-token-not-used",
        "MIRROR_FORBIDDEN_HOSTS": "203.0.113.77",
        "TMPDIR": str(tmp_path),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), "--remote", str(bare), "--product", "prod-test00000000",
         "--source", str(src), "--live-url", "https://example.com"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


def _commits(bare: Path) -> int:
    return int(_git("--git-dir", str(bare), "rev-list", "--count", "main").strip())


def test_a_product_carrying_a_token_is_never_pushed(tmp_path):
    bare = _remote(tmp_path)
    src = _product(tmp_path, 'OPENROUTER_KEY = "sk-or-v1-' + "a1b2c3d4" * 6 + '"\n')
    out = _publish(tmp_path, bare, src)
    assert out.returncode != 0, out.stdout + out.stderr
    assert "secret scan" in out.stderr
    assert _commits(bare) == 1  # the seed only


def test_a_key_file_is_left_out_of_the_tree(tmp_path):
    bare = _remote(tmp_path)
    src = _product(tmp_path, "print('ok')\n")
    (src / "deploy_key.pem").write_text("not a real key\n", encoding="utf-8")
    (src / "signing_key").write_bytes(os.urandom(64))
    out = _publish(tmp_path, bare, src)
    assert out.returncode == 0, out.stdout + out.stderr
    files = _git("--git-dir", str(bare), "ls-tree", "-r", "--name-only", "main")
    assert "products/prod-test00000000/app.py" in files
    assert "deploy_key.pem" not in files and "signing_key" not in files


def test_a_clean_product_is_published(tmp_path):
    bare = _remote(tmp_path)
    src = _product(tmp_path, "print('hello')\n")
    out = _publish(tmp_path, bare, src)
    assert out.returncode == 0, out.stdout + out.stderr
    assert _commits(bare) == 2
