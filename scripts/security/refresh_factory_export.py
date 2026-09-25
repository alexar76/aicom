#!/usr/bin/env python3
"""Atomically refresh the Hub's read-only catalog from the running Factory."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from export_factory_catalog import public_products


def own_dir(path):
    """Create or adopt an export directory that only this user can change.

    This runs as root and writes into the directory, so one that anybody else can write
    (or a symlink to somewhere else) would let them steer root's writes. The mode is set
    explicitly on every run: mkdir's mode is masked by the umask, and a root shell with
    umask 077 used to leave the export unreadable to the hub's non-root user.
    """
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode):
        raise RuntimeError(f"{path} is not a directory (a symlink?); refusing to export into it")
    if st.st_uid != os.geteuid() or st.st_mode & 0o022:
        raise RuntimeError(f"{path} must be owned by uid {os.geteuid()} and writable only by it")
    os.chmod(path, 0o755)


def snapshot_size(path):
    """Products in the current snapshot; 0 when there is none or it cannot be read."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            return len(json.load(f).get("products") or {})
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--container", default="aicom-app-1")
    ap.add_argument("--destination", type=Path, default=Path("/var/lib/aicom/hub-catalog"))
    ap.add_argument("--allow-empty", action="store_true",
                    help="let an empty Factory export replace a non-empty snapshot")
    args = ap.parse_args()
    script = Path(__file__).with_name("export_factory_catalog.py").read_bytes()
    command = "import sys; __file__='/app/scripts/security/export_factory_catalog.py'; exec(compile(sys.stdin.read(), __file__, 'exec'))"
    result = subprocess.run(["docker", "exec", "-i", "-e", "PYTHONPATH=/app:/app/aimarket-hub",
        args.container, "python", "-c", command], input=script, capture_output=True, timeout=30)
    if result.returncode:
        # The container's traceback is the only record of why the export failed.
        sys.stderr.write(result.stderr.decode("utf-8", "replace")[-4000:])
        raise RuntimeError("Factory catalog export failed; keeping previous snapshot")
    payload = json.loads(result.stdout)
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, dict) or not all(isinstance(p, dict) for p in products.values()):
        raise ValueError("Invalid catalog export")
    # The allow-list already ran inside the Factory. Apply it again here, where the file
    # the hub reads is written, so whatever that side prints, only catalog fields reach it.
    body = json.dumps({"products": public_products(products)}, ensure_ascii=False).encode()

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    own_dir(args.destination)
    state = args.destination / "state"
    own_dir(state)
    target = state / "pipeline.json"
    previous = snapshot_size(target)
    if not products and previous and not args.allow_empty:
        raise RuntimeError(f"Factory export is empty but the current snapshot lists {previous} "
                           "products; keeping it (pass --allow-empty if that is intended)")
    # A fresh, unpredictable name: a fixed temp name could be pre-planted as a symlink,
    # and root would then truncate and chmod whatever it points at.
    fd, temp = tempfile.mkstemp(dir=state, prefix=".pipeline.json.")
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp)
        raise
    print(f"Exported {len(products)} products")


if __name__ == "__main__":
    main()
