#!/usr/bin/env python3
"""Second overlay of 2026-11-16 (main 6dbfb7fb3): code-20261116 -> code-20261116b on the three containers.

    python3 switch_b.py apply      # build is separate (see README); swap tags, recreate --no-deps
    python3 switch_b.py rollback   # back to code-20261116 from the *.pre-b backups
"""
import shutil
import subprocess
import sys
from pathlib import Path

MOMUS_COMPOSE = Path("/root/momus-deploy/docker-compose.prod.yml")
FIX_COMPOSE = Path("/root/aicom/docker-compose.remediation-fix.yml")
SWAPS = {MOMUS_COMPOSE: ("momus-backend-code-20261116 ", "skopos-remediation-code-20261116 "),
         FIX_COMPOSE: ("remediation-fixer-code-20261116 ",)}


def run(*cmd: str) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def recreate() -> None:
    run("docker", "compose", "-p", "momus-deploy", "-f", str(MOMUS_COMPOSE), "up", "-d", "--no-deps",
        "momus-backend", "skopos-remediation")
    run("docker", "compose", "-p", "aicom", "-f", str(FIX_COMPOSE), "up", "-d", "--no-deps", "remediation-fixer")


def apply() -> None:
    for path, tags in SWAPS.items():
        text = path.read_text()
        backup = path.with_name(path.name + ".pre-b")
        if not backup.exists():
            shutil.copy2(path, backup)
        for tag in tags:
            if text.count(tag) != 1:
                sys.exit(f"{path}: expected exactly one '{tag.strip()}', found {text.count(tag)}")
            text = text.replace(tag, tag.strip() + "b ")
        path.write_text(text)
    recreate()


def rollback() -> None:
    for path in SWAPS:
        backup = path.with_name(path.name + ".pre-b")
        shutil.copy2(backup, path)
    recreate()


if __name__ == "__main__":
    {"apply": apply, "rollback": rollback}[sys.argv[1]]()
