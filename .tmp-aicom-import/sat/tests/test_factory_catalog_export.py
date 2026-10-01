"""The hub's read-only Factory catalog export (scripts/security/refresh_factory_export.py).

The hub used to mount the whole Factory data tree at /factory_data. It now mounts only
the export this script writes. These tests run the real script on the host side with a
fake `docker` on PATH, and check two things: the export directory cannot be turned
against the root user that writes it, and a hub reading only the export does everything
it did with the full tree mounted.
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REFRESH = ROOT / "scripts" / "security" / "refresh_factory_export.py"
HUB_SRC = ROOT / "aimarket-hub"

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX modes and symlinks")

FAKE_DOCKER = """\
#!{python}
# Test double for `docker exec -i ... <factory> python -c <cmd>`.
import os, subprocess, sys
args = sys.argv[1:]
if args[:1] != ["exec"]:
    sys.exit("fake docker: unexpected " + " ".join(args))
if os.environ.get("FAKE_FACTORY_DATA_ROOT"):
    # Run the export the way the Factory container does: repo importable, its data root set.
    env = {{k: v for k, v in os.environ.items()
           if k not in ("SQLITE_PATH", "AICOM_PIPELINE_JSON", "AIFACTORY_STATE_DIR")}}
    env["PYTHONPATH"] = os.environ["FAKE_FACTORY_PYTHONPATH"]
    env["AIFACTORY_DATA_ROOT"] = os.environ["FAKE_FACTORY_DATA_ROOT"]
    cmd = args[args.index("-c") + 1]
    sys.exit(subprocess.run([sys.executable, "-c", cmd], env=env).returncode)
sys.stdin.read()
sys.stdout.write(open(os.environ["FAKE_DOCKER_STDOUT"]).read())
sys.stderr.write(os.environ.get("FAKE_DOCKER_STDERR", ""))
sys.exit(int(os.environ.get("FAKE_DOCKER_RC", "0")))
"""

CATALOG = {"products": {
    "prod-a": {"id": "prod-a", "name": "Ledger Sync API", "state": "COMPLETED",
               "idea": "api service"},
    "prod-b": {"id": "prod-b", "name": "Scheduling SaaS", "state": "DEPLOYED_PRODUCTION"},
}}


@pytest.fixture
def host(tmp_path):
    """A fake docker on PATH plus a helper that runs the refresh script like the deploys do."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER.format(python=sys.executable))
    docker.chmod(0o755)
    stdout_file = tmp_path / "factory_stdout.json"
    stdout_file.write_text(json.dumps(CATALOG))
    dest = tmp_path / "hub-catalog"

    def run(*extra, umask=None, **env):
        full_env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_DOCKER_STDOUT": str(stdout_file), **env}
        return subprocess.run(
            [sys.executable, str(REFRESH), "--destination", str(dest), *extra],
            env=full_env, capture_output=True, text=True, timeout=120,
            preexec_fn=(lambda: os.umask(umask)) if umask is not None else None,
        )

    return {"run": run, "dest": dest, "stdout": stdout_file, "tmp": tmp_path}


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def _snapshot(dest: Path) -> dict:
    return json.loads((dest / "state" / "pipeline.json").read_text())


# ── Writing the export as root ──────────────────────────────────────────────────


def test_a_symlink_planted_at_the_temp_name_is_not_followed(host):
    dest, tmp = host["dest"], host["tmp"]
    (dest / "state").mkdir(parents=True)
    victim = tmp / "victim"
    victim.write_text("ROOT-ONLY-SECRET")
    victim.chmod(0o600)
    (dest / "state" / "pipeline.json.tmp").symlink_to(victim)

    result = host["run"]()
    assert result.returncode == 0, result.stderr
    assert victim.read_text() == "ROOT-ONLY-SECRET"
    assert _mode(victim) == 0o600
    target = dest / "state" / "pipeline.json"
    assert not target.is_symlink()
    assert set(_snapshot(dest)["products"]) == {"prod-a", "prod-b"}


@pytest.mark.parametrize("which", ["root", "state"])
def test_refuses_an_export_directory_someone_else_can_write(host, which):
    dest = host["dest"]
    (dest / "state").mkdir(parents=True)
    os.chmod(dest if which == "root" else dest / "state", 0o777)

    result = host["run"]()
    assert result.returncode != 0
    assert "writable only by it" in result.stderr
    assert not (dest / "state" / "pipeline.json").exists()


def test_refuses_a_symlinked_state_directory(host):
    dest, tmp = host["dest"], host["tmp"]
    elsewhere = tmp / "elsewhere"
    elsewhere.mkdir()
    dest.mkdir()
    (dest / "state").symlink_to(elsewhere, target_is_directory=True)

    result = host["run"]()
    assert result.returncode != 0
    assert "not a directory" in result.stderr
    assert list(elsewhere.iterdir()) == []


def test_modes_are_hub_readable_whatever_the_umask(host):
    dest = host["dest"]
    result = host["run"](umask=0o077)
    assert result.returncode == 0, result.stderr
    assert _mode(dest) == 0o755
    assert _mode(dest / "state") == 0o755
    assert _mode(dest / "state" / "pipeline.json") == 0o644

    # A tree left 0700 by an earlier run under a strict umask is corrected, not trusted.
    os.chmod(dest / "state", 0o700)
    os.chmod(dest, 0o700)
    assert host["run"](umask=0o077).returncode == 0
    assert _mode(dest) == _mode(dest / "state") == 0o755


# ── What the Factory side is allowed to put in front of the hub ─────────────────


def test_the_host_reapplies_the_field_allow_list(host):
    host["stdout"].write_text(json.dumps({
        "products": {"prod-x": {
            "name": "Kept", "state": "COMPLETED",
            "spec": {"api_key": "CANARY_UNFILTERED"},
            "capabilities": [{"id": "c1", "name": "c1", "invoke_url": "https://x",
                              "headers": {"Authorization": "CANARY_HEADER"}}],
        }},
        "dump": {"JWT_SECRET_KEY": "CANARY_TOPLEVEL"},
    }))
    result = host["run"]()
    assert result.returncode == 0, result.stderr
    raw = (host["dest"] / "state" / "pipeline.json").read_text()
    assert "CANARY_" not in raw
    assert json.loads(raw) == {"products": {"prod-x": {
        "name": "Kept", "state": "COMPLETED", "id": "prod-x",
        "capabilities": [{"id": "c1", "name": "c1"}],
    }}}


@pytest.mark.parametrize("payload", [[], {"products": []}, {"products": {"p": "not-a-row"}}])
def test_a_malformed_export_changes_nothing(host, payload):
    assert host["run"]().returncode == 0
    before = _snapshot(host["dest"])
    host["stdout"].write_text(json.dumps(payload))
    result = host["run"]()
    assert result.returncode != 0
    assert "Invalid catalog export" in result.stderr
    assert _snapshot(host["dest"]) == before


def test_an_empty_export_does_not_wipe_a_good_catalogue(host):
    assert host["run"]().returncode == 0
    host["stdout"].write_text(json.dumps({"products": {}}))

    refused = host["run"]()
    assert refused.returncode != 0
    assert "--allow-empty" in refused.stderr
    assert set(_snapshot(host["dest"])["products"]) == {"prod-a", "prod-b"}

    allowed = host["run"]("--allow-empty")
    assert allowed.returncode == 0, allowed.stderr
    assert _snapshot(host["dest"]) == {"products": {}}


def test_a_failed_export_says_why_and_keeps_the_snapshot(host):
    assert host["run"]().returncode == 0
    result = host["run"](FAKE_DOCKER_RC="1",
                         FAKE_DOCKER_STDERR="Traceback: sqlite3.OperationalError CANARY_REASON\n")
    assert result.returncode != 0
    assert "CANARY_REASON" in result.stderr
    assert "keeping previous snapshot" in result.stderr
    assert set(_snapshot(host["dest"])["products"]) == {"prod-a", "prod-b"}


# ── Parity: a hub reading only the export sees what it saw with the full tree ────


def _build_factory_tree(root: Path) -> None:
    """A Factory data tree with the shapes the loader reads, plus things the hub must not get."""
    state = root / "state"
    state.mkdir(parents=True)
    con = sqlite3.connect(state / "pipeline.db")
    con.execute("CREATE TABLE products (id TEXT PRIMARY KEY, idea TEXT, state TEXT, "
                "category TEXT, spec TEXT, tags TEXT, error TEXT, created_at TEXT, "
                "updated_at TEXT)")
    rows = [
        ("prod-a", "SaaS dashboard with a REST API and an automation agent", "COMPLETED",
         "", json.dumps({"api_key": "CANARY_SPEC_KEY"}), json.dumps(["b2b"]), None, "t0", "t1"),
        ("prod-b", "Marketing landing one-pager for a bakery", "DEPLOYED_PRODUCTION",
         "food", None, None, None, "t0", "t1"),
        ("prod-c", "SaaS that never shipped", "FAILED", "", None, None, "boom", "t0", "t1"),
    ]
    con.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    (state / "pipeline.json").write_text(json.dumps({"products": {
        # The SQLite row wins for prod-a, exactly as in the Factory.
        "prod-a": {"state": "FAILED", "name": "stale json copy"},
        "prod-d": {"state": "COMPLETED", "name": "Tray Timer (3)",
                   "idea": "desktop electron system tray app with an api",
                   "license_key": "CANARY_LICENSE",
                   "capabilities": [{"id": "tray.static@v1", "name": "tray.static",
                                     "prompt_template": "{\"static\": true}",
                                     "invoke_url": "https://factory.invalid/tray",
                                     "headers": {"Authorization": "CANARY_HDR"}}]},
    }}))
    (state / "prod-a").mkdir()
    (state / "prod-a" / "marketing_content.json").write_text(json.dumps(
        {"marketing": {"product_name": "Ledger Sync Suite", "category": "fintech"}}))
    (root / "specs" / "prod-b").mkdir(parents=True)
    (root / "specs" / "prod-b" / "specification.json").write_text(json.dumps(
        {"specification": {"product_name": "Bakery Page", "delivery_profile": "static_site"}}))
    (root / "secrets" / "llm").mkdir(parents=True)
    (root / "secrets" / "llm" / "openai_api_key").write_text("CANARY_SECRET_FILE")
    (root / "hub_signing_key").write_text("CANARY_SIGNING_KEY")
    (root / "config").mkdir()
    (root / "config" / "stripe.json").write_text('{"key": "CANARY_STRIPE"}')
    # The Factory's own ACEX code creates <data_root>/data; the old mount relied on it.
    (root / "data").mkdir()


HUB_VIEW = textwrap.dedent("""\
    import contextlib, json, os, sqlite3, sys
    from pathlib import Path

    out = {"importable": []}
    for name in ("web", "core"):  # the hub image ships neither
        try:
            __import__(name)
            out["importable"].append(name)
        except ImportError:
            pass

    import aimarket_hub.db_backend as backend_mod

    class FakePostgres:
        backend_type = "postgresql"
        def __init__(self):
            self.conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        @contextlib.contextmanager
        def get_connection(self):
            yield self.conn

    real_create = backend_mod.create_backend
    def create_backend(database_url="", db_path=None):
        if database_url.startswith("postgresql://"):
            return FakePostgres()
        return real_create(database_url=database_url, db_path=db_path)
    backend_mod.create_backend = create_backend

    from aimarket_hub.database import HubDatabase
    from aimarket_hub.factory_bridge import _capability_rows_for_product, import_factory_products
    from aimarket_hub.factory_products_loader import iter_shipped_factory_products

    root = Path(os.environ["AIFACTORY_DATA_ROOT"])
    work = Path(sys.argv[1])
    # deploy_hub.sh's post-start step: an explicit path, /factory_data/state/pipeline.json.
    path = root / "state" / "pipeline.json"
    products = iter_shipped_factory_products(str(path))
    out["products"] = {pid: {k: p.get(k) for k in ("name", "idea", "state", "category",
                                                  "delivery_profile")}
                       for pid, p in products.items()}
    out["capabilities"] = {pid: _capability_rows_for_product(pid, p) for pid, p in products.items()}
    out["deploy_import"] = import_factory_products(HubDatabase(str(work / "a.db")), str(path))
    # create_app's own call, with its relative default.
    out["startup_import"] = import_factory_products(HubDatabase(str(work / "b.db")))

    # The two ACEX calls every paid invoke makes, against the configured PostgreSQL URL.
    from aimarket_hub import acex_audit, acex_ipo
    try:
        acex_ipo.float_product("prod-a", name="Ledger Sync Suite", audit_score_bps=8000)
        out["acex"] = [acex_ipo.accrue_revenue("prod-a", 1.0).get("ok"),
                       acex_audit.accrue_audit_rewards("prod-a", 1.0).get("ok")]
    except Exception as exc:
        out["acex"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(out, sort_keys=True))
""")


def _read_only(root: Path, writable: bool) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            continue
        if path.is_dir():
            os.chmod(path, 0o755 if writable else 0o555)
        else:
            os.chmod(path, 0o644 if writable else 0o444)


def _hub_view(root: Path, work: Path) -> dict:
    """Load `root` the way the hub container does: only aimarket_hub importable, root read-only."""
    work.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "SQLITE_PATH", "DATABASE_URL", "AICOM_PIPELINE_JSON",
                        "AIFACTORY_STATE_DIR", "ACEX_IPO_DB_PATH", "ACEX_AUDIT_DB_PATH")}
    env.update({
        "PYTHONPATH": str(HUB_SRC),
        "AIFACTORY_DATA_ROOT": str(root),
        "AIFACTORY_PROD": "1",
        "AIMARKET_ACEX_IPO_DATABASE_URL": "postgresql://acex:unused@db.invalid:5432/acex",
        "AIMARKET_ACEX_AUDIT_DATABASE_URL": "postgresql://acex:unused@db.invalid:5432/acex",
    })
    _read_only(root, writable=False)
    try:
        result = subprocess.run([sys.executable, "-c", HUB_VIEW, str(work)], cwd=work, env=env,
                                capture_output=True, text=True, timeout=180)
    finally:
        _read_only(root, writable=True)
    assert result.returncode == 0, result.stderr[-3000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_hub_keeps_every_capability_reading_only_the_export(host):
    tmp = host["tmp"]
    factory = tmp / "factory-data"
    _build_factory_tree(factory)

    result = host["run"](FAKE_FACTORY_DATA_ROOT=str(factory),
                         FAKE_FACTORY_PYTHONPATH=os.pathsep.join([str(ROOT), str(HUB_SRC)]))
    assert result.returncode == 0, result.stderr
    assert "Exported 3 products" in result.stdout

    export = host["dest"]
    assert sorted(str(p.relative_to(export)) for p in export.rglob("*")) == [
        "state", "state/pipeline.json"]
    assert "CANARY_" not in (export / "state" / "pipeline.json").read_text()

    with_full_tree = _hub_view(factory, tmp / "hub-full")
    with_export = _hub_view(export, tmp / "hub-export")

    assert with_full_tree["importable"] == [], "the hub view must not see web/ or core/"
    assert set(with_full_tree["products"]) == {"prod-a", "prod-b", "prod-d"}
    assert with_full_tree["products"]["prod-a"]["name"] == "Ledger Sync Suite"
    assert with_full_tree["products"]["prod-b"]["delivery_profile"] == "static_site"
    assert any(with_full_tree["capabilities"].values())
    assert with_full_tree["acex"] == [True, True]
    assert with_export == with_full_tree
