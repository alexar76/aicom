# Smoke test of the pause in the overlay image, on a throwaway data dir (never /data).
import os, tempfile
from dataclasses import replace, fields
from pathlib import Path
d = Path(tempfile.mkdtemp()); os.environ["HELIOS_DATA_DIR"] = str(d)
from helios.config import load_config
from helios.queue import QueueStore
from helios import worker
names = {f.name for f in fields(load_config(d / "missing.yaml"))}
over = {k: v for k, v in dict(data_dir=d, dry_run=False, auto_approve=False, director_enabled=False,
        calliope_enabled=False, calliope_editorial_enabled=False).items() if k in names}
cfg = replace(load_config(d / "missing.yaml"), **over)
store = QueueStore(d)
job = store.enqueue(template="release-short", idempotency_key="smoke:1")
attempts = []
def refused(cfg, store, job, audit, director):
    attempts.append(job.id)
    raise RuntimeError("HttpError 400 uploadLimitExceeded")
worker.process_job = refused
r1 = worker.run_worker(cfg); r2 = worker.run_worker(cfg); r3 = worker.run_worker(cfg)
print("exit codes", r1, r2, r3, "| attempts", len(attempts), "| status", store.get_job(job.id).status,
      "| paused_until", store.uploads_paused_until())
assert attempts == [job.id] and store.get_job(job.id).status == "pending" and store.uploads_paused_until()
st = store.load_upload_state(); st["paused_until"] = "2000-01-01T00:00:00Z"; store.save_upload_state(st)
worker.run_worker(cfg)
assert len(attempts) == 2
print("SMOKE-OK")
