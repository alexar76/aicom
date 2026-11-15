# Smoke test: the real 2026-11-08 description must reach the reviewer whole (read-only copy of the job).
import json, sys, tempfile
from dataclasses import fields, replace
from pathlib import Path
from helios.config import load_config
from helios.director import Director
from helios.queue import Job, QueueStore
from helios.calliope import _cut_on_space
job_d = json.load(sys.stdin)
d = Path(tempfile.mkdtemp())
cfg = load_config(d / "missing.yaml")
cfg = replace(cfg, **{k: v for k, v in dict(data_dir=d, director_enabled=False).items() if k in {f.name for f in fields(cfg)}})
director = Director(cfg, QueueStore(d))
seen = []
class Stub:
    def json_chat(self, messages):
        seen.append(messages[-1]["content"]); return {"approve": True, "reason": "ok", "priority": 50}
director.llm = Stub()
job = Job(id="smoke", idempotency_key="smoke", status="pending", template=job_d["template"], youtube=job_d["youtube"])
director.review_metadata(job)
desc = job_d["youtube"]["description"]
print("description chars:", len(desc), "| reviewer got the end:", repr(seen[0][-40:]))
assert seen[0].endswith(desc) and desc.endswith("https://oracles.modelmarket.dev")
assert _cut_on_space("a" * 3995 + " https://oracles.modelmarket.dev", 4000) == "a" * 3995
print("SMOKE-OK")
