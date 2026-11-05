#!/usr/bin/env python3
"""Run on attested as root, from this folder: python3 -I db_reader.py

Creates the provider's read-only database role and function in Multica's Postgres (db_reader.sql), writes
MULTICA_DB_DSN into /opt/multica/secrets/provider.env (0600, backup first), and checks as that role that the
function answers while the tables themselves are refused. The password goes to psql through stdin only;
nothing secret is printed."""
import os
import secrets
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV = Path("/opt/multica/secrets/provider.env")
PG = "multica-postgres-1"
ROLE = "multica_provider_ro"


def run(args, stdin=""):
    return subprocess.run(args, input=stdin, text=True, capture_output=True)


lines = ENV.read_text().splitlines()
dsn = next((l.split("=", 1)[1] for l in lines if l.startswith("MULTICA_DB_DSN=")), "")
password = dsn.split(":", 2)[2].split("@", 1)[0] if dsn else secrets.token_hex(24)
db = run(["docker", "exec", PG, "printenv", "POSTGRES_DB"]).stdout.strip() or "multica"

sql = f"\\set pw '{password}'\n" + (HERE / "db_reader.sql").read_text()
r = run(["docker", "exec", "-i", PG, "sh", "-c", f'psql -U "$POSTGRES_USER" -d {db} -q -v ON_ERROR_STOP=1'], sql)
if r.returncode:
    raise SystemExit("db_reader.sql failed: " + r.stderr.replace(password, "<pw>")[-800:])
print("role and function in place:", ROLE, "provider_ro.order_answers(text)")

if not dsn:
    shutil.copy2(ENV, ENV.with_name("provider.env.bak-20261104-v2"))
    # The container name, not the service name: the provider is also on the hub network, where `postgres` is the
    # hub's own database (the first roll hit it, 2026-11-05).
    dsn = f"postgresql://{ROLE}:{password}@multica-postgres-1:5432/{db}"
    fd = os.open(ENV, os.O_WRONLY | os.O_TRUNC)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines + [f"MULTICA_DB_DSN={dsn}"]) + "\n")
    os.chmod(ENV, 0o600)
    print("written name: MULTICA_DB_DSN ->", ENV)

check = (f"read PGPASSWORD; export PGPASSWORD; "
         f"psql -h multica-postgres-1 -U {ROLE} -d {db} -At -c \"select count(*) from provider_ro.order_answers('job_687b914aba1fd2ca1cf103d94c9f68e5')\"; "
         f"psql -h multica-postgres-1 -U {ROLE} -d {db} -At -c 'select count(*) from public.issue' 2>&1 | head -1")
r = run(["docker", "exec", "-i", PG, "sh", "-c", check], password + "\n")
out = r.stdout.replace(password, "<pw>").strip().splitlines()
print("function rows for the MY-62 job (first design, so its task matches):", out[0] if out else "?")
print("direct table read as the role:", out[1] if len(out) > 1 else "?")
if len(out) < 2 or "permission denied" not in out[1]:
    raise SystemExit("the role can read the table directly, or the check failed: stop and look")
