#!/usr/bin/env python3
"""Third overlay (main 443f0f422): momus-backend code-20261116b -> code-20261117.
    python3 switch_c.py apply | rollback"""
import shutil, subprocess, sys
from pathlib import Path
C = Path("/root/momus-deploy/docker-compose.prod.yml")
OLD, NEW = "momus-backend-code-20261116b ", "momus-backend-code-20261117 "
def recreate():
    subprocess.run(["docker", "compose", "-p", "momus-deploy", "-f", str(C), "up", "-d", "--no-deps", "momus-backend"], check=True)
def apply():
    t = C.read_text(); b = C.with_name(C.name + ".pre-c")
    if not b.exists(): shutil.copy2(C, b)
    if t.count(OLD) != 1: sys.exit(f"expected one '{OLD.strip()}', found {t.count(OLD)}")
    C.write_text(t.replace(OLD, NEW)); recreate()
def rollback():
    shutil.copy2(C.with_name(C.name + ".pre-c"), C); recreate()
if __name__ == "__main__":
    {"apply": apply, "rollback": rollback}[sys.argv[1]]()
