#!/usr/bin/env python3
"""Load factory vs satellite paths from scripts/satellite-map.yaml."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

MAP_PATH = Path(__file__).resolve().parent / "satellite-map.yaml"

DEFAULT_RSYNC_EXCLUDES = [
    ".git",
    ".claude",
    ".cursor",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".dart_tool",
    "build",
    "dist",
    "target",  # Rust/Cargo build trees (e.g. awr/rust/target) — tens of thousands of files
    ".ruff_cache",
    ".hypothesis",
    ".mesh_data",
    "data/prometheus",  # local Prometheus TSDB chunks — binary tombstones trip key-shape guard
    "data/signal-hunt",  # local hunt runtime (session_secret, signing key, sqlite) — gitignored; rsync still sees it
    # ── Secrets: NEVER rsync to the public mirror ──────────────────────────
    # rsync copies the working tree directly, so .gitignore does NOT protect
    # the mirror — these patterns are the only thing standing between local
    # secrets and a public push. Keep aligned with .gitignore's secret rules.
    ".env",
    ".env.*",
    "session_secret",  # raw hub/game session seeds (e.g. data/signal-hunt/session_secret)
    "data/secrets",
    "*.key",
    "*.pem",
    # `*.key` does NOT match `<service>_signing_key`, which is how every Ed25519 key in this
    # ecosystem is named. Added after finding the pre-publish guard blind to raw binary key files.
    "*_signing_key",
    # …and `*_signing_key` did not match `data/.treasury_scanner_ref_key`, which reached the
    # publish tree and was stopped only by verify_mirror_secrets. This list had drifted from the
    # one in mirror_satellites.sh — two parallel secret lists, and this copy was missing
    # dataset_salt, *.pem, *_vrf_sk and .env.* as well. `*_key` is the general form; keep it,
    # and keep the narrower patterns above it so the intent of each stays readable.
    # Nothing tracked by git matches these, so the mirror loses no real content.
    "*_key",
    "*_vrf_sk",
    "dataset_salt",
    "*_ed25519",
    "conductor_key",
    "data/remediation",
    "*.enc",
    "EXTRACTION_REPORT.md",
    "data/state",
    "data/channels.db",
    "data/channels.db-shm",
    "data/channels.db-wal",
    ":memory:",
    ":memory:-wal",
    ":memory:-shm",
    "*.sqlite3",
    "*.sqlite3-wal",
    "*.sqlite3-shm",
    "data/funnel",
    "data/signups.json",
    "web/frontend/test-results",
    "web/frontend/tsconfig.tsbuildinfo",
    "contracts/zk/.tools",
    "contracts/evm/broadcast",
    "*.egg-info",
    # Held only by the shell mirror before the two lists were reconciled. The comment in
    # scripts/mirror_satellites.sh has always said "keep aligned with
    # scripts/aicom_publish_config.py"; they had drifted by 21 patterns, including
    # `*_key`, `conductor_key`, `*_ed25519` and `session_secret` — i.e. the shell path
    # would have shipped key material the Python path excluded. The shell now READS this
    # list instead of keeping a copy, so the drift cannot come back.
    ".DS_Store",
    "broadcast",
    # On Gitea (full monorepo), not on public GitHub. Satellite mirrors rsync
    # from this list (list-rsync-excludes), not from FACTORY_LOCAL_EXCLUDES.
    "independent",
    # Pantheon art portal (pantheon.modelmarket.dev) — Gitea only; not a GH satellite.
    "pantheon",
    # Raw key seed kept next to logos/ for operator use. gitignore is not
    # enough: satellite rsync copies the working tree, not `git ls-files`.
    "unused",
]

# Never rsync to public factory remote (alexar76/aicom). Monorepo .gitignore covers
# local git only — publish_aicom_factory.sh uses rsync, not git add.
# Keep aligned with .dockerignore (IDE/CI) and mirror_satellites.sh hygiene.
FACTORY_LOCAL_EXCLUDES = [
    ".cursor",
    ".claude",
    ".gitea",
    ".github",  # monorepo-only mirror workflows; factory gets ci/pages/security-scan + ISSUE_TEMPLATE via publish_aicom_factory.sh
    "ecosystem-README.md",  # ecosystem-root overview — the public factory repo (alexar76/aicom) keeps its own README.md
    "scripts/gitea-targets.yaml",  # internal Gitea hosts/IPs — must never reach the public mirror
    "scripts/scrub_private_hosts.sh",  # contains private-host needles by design; never ship to public factory
    "docs/gitea-publishing.md",  # internal ops memo (references internal Gitea hosts)
    "data/channels.db",  # local SQLite runtime — never mirror to public factory
    "data/signal-hunt",  # local hunt runtime secrets/DB — never mirror to public factory
    "contracts/zk/.tools",
    "contracts/evm/broadcast",  # Foundry broadcast artifacts (gitignored locally; rsync still sees them)
    "data/funnel",
    "data/signups.json",
    "web/frontend/test-results",
    "web/frontend/tsconfig.tsbuildinfo",
    # ── Secret belt-and-braces (also in DEFAULT_RSYNC_EXCLUDES) ─────────────
    # Duplicated here so a future refactor that drops one list still blocks
    # secrets from reaching the public mirror.
    ".env",
    "session_secret",
    "data/secrets",
    "*.key",
    "*.enc",
    "contracts/solana/keys",  # Solana program/deploy keypairs — never reach the public mirror
    # Ed25519 signing keys are named `<service>_signing_key`, NOT `*.key`, so the pattern above never
    # matched a single one of them. They survived only because the mirror commits from the git index
    # and .gitignore happened to cover them — and `data/remediation/` was one path it did not cover,
    # leaving the conductor's key (it signs the DeployOrders a node agent executes) exposed to any
    # publish run. Explicit patterns, because "it is gitignored" is one layer, not three.
    "*_signing_key",
    "*_ed25519",
    "conductor_key",
    "data/remediation",  # conductor signing key + A2A observer DB + deploy-order journal
    "EXTRACTION_REPORT.md",
    # Build artifacts — regenerate via school/build.py / deploy_edu_school.sh
    "edu-landing",
    # Tracked on Gitea; stripped from the public GitHub factory/satellite rsync.
    "independent",
    "pantheon",
    # Attested Memory SaaS + deploy contour — Gitea only until satellites are
    # explicitly flipped github_published. Never ship host/deploy runbooks,
    # compose wiring, or product-shell trees on the public factory mirror.
    "SAAS_PROJECTS.md",
    "saas-compose.yml",
    "saas-edge",
    "saas-landing",
    "scripts/deploy_attested_memory.sh",
    "personal-attested-memory",
    "team-memory-os",
    "expert-memory-market",
]


def _load_map() -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required: pip install pyyaml")
    if not MAP_PATH.is_file():
        raise FileNotFoundError(MAP_PATH)
    return yaml.safe_load(MAP_PATH.read_text(encoding="utf-8")) or {}


def satellite_export_paths() -> list[str]:
    """Monorepo paths that belong in separate GitHub repos (not in factory)."""
    data = _load_map()
    paths: list[str] = []
    for sat in data.get("satellites") or []:
        if sat.get("id") == "aicom":
            continue
        # Opt-in dual-publish (rare): keep path on the public factory tree AND
        # mirror as a satellite. Prefer dedicated satellite repos instead.
        if sat.get("keep_on_factory"):
            continue
        for p in sat.get("paths") or []:
            if p == "plugins:plugins":
                paths.append("plugins")
            elif isinstance(p, str) and p.startswith("plugins:"):
                paths.append(p.split(":", 1)[1])
            elif p == ".":
                continue
            else:
                paths.append(str(p).rstrip("/"))
        for extra in (sat.get("export_layout") or {}).get("extra") or []:
            if isinstance(extra, dict) and extra.get("from"):
                paths.append(str(extra["from"]).rstrip("/"))
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return sorted(out)


def satellite_path_to_repo() -> dict[str, str]:
    """Monorepo path → the GitHub repo that publishes it.

    A doc that links to `../gaia/docs/…` 404s on the factory mirror, which strips
    gaia/; the link has to point at alexar76/gaia instead. Deriving the mapping here
    means a new satellite is link-fixable the moment it is registered in the map —
    the hand-maintained copy in fix_whitepaper_satellite_links.py had drifted to 15
    of 30+ satellites, so 22 docs stayed unfixable.
    """
    data = _load_map()
    out: dict[str, str] = {}
    for sat in data.get("satellites") or []:
        repo = sat.get("repo")
        if not repo or sat.get("id") == "aicom" or sat.get("keep_on_factory"):
            continue
        for p in sat.get("paths") or []:
            if not isinstance(p, str) or p == ".":
                continue
            path = p.split(":", 1)[1] if p.startswith("plugins:") else p
            out.setdefault(path.rstrip("/"), str(repo))
    # Vendored paths (logos ships oracles/core, aimarket-plugins ships a hub plugin)
    # must not steal links: a link into oracles/core belongs to alexar76/oracles, the
    # repo that owns the folder, not to the satellite that happens to embed a copy.
    owned = set(out)
    return {
        path: repo
        for path, repo in out.items()
        if not any(path != other and path.startswith(other + "/") for other in owned)
    }


def factory_exclude_paths() -> list[str]:
    """Paths stripped from aicom factory remote."""
    data = _load_map()
    explicit: list[str] = []
    for sat in data.get("satellites") or []:
        if sat.get("id") == "aicom":
            explicit.extend(str(p).rstrip("/") for p in sat.get("exclude_paths") or [])
            break
    return sorted(dict.fromkeys([*explicit, *satellite_export_paths()]))


def factory_local_exclude_paths() -> list[str]:
    return list(FACTORY_LOCAL_EXCLUDES)


def factory_submodule_paths() -> list[str]:
    return []


def rsync_exclude_args() -> list[str]:
    args: list[str] = []
    for p in DEFAULT_RSYNC_EXCLUDES:
        args.extend(["--exclude", p])
    for p in factory_local_exclude_paths():
        args.extend(["--exclude", p])
    for p in factory_submodule_paths():
        args.extend(["--exclude", f"{p}/"])
    for p in factory_exclude_paths():
        args.extend(["--exclude", f"/{p}/"])
    return args


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list-excludes"
    if cmd == "list-excludes":
        for p in factory_exclude_paths():
            print(p)
        return 0
    if cmd == "list-rsync-excludes":
        # Consumed by scripts/mirror_satellites.sh. One pattern per line, no shell quoting:
        # the caller reads them into an array, so globs must NOT be expanded here.
        for p in DEFAULT_RSYNC_EXCLUDES:
            print(p)
        return 0
    if cmd == "list-local-excludes":
        for p in factory_local_exclude_paths():
            print(p)
        return 0
    if cmd == "list-submodules":
        for p in factory_submodule_paths():
            print(p)
        return 0
    if cmd == "rsync-args":
        for arg in rsync_exclude_args():
            print(arg)
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
