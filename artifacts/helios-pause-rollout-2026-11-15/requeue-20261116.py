# One-shot (2026-11-16 06:00Z, owner's yes 2026-11-15): re-queue the Platon UMBRAL episode whose upload
# hit YouTube's channel upload cap on 2026-11-15 (job_20261115_28a2bb55; the render was OK).
# Runs inside helios-worker. Uploads PRIVATE (HELIOS_AUTO_APPROVE=0): publishing needs `helios approve`.
# Skips if the channel already has >= 10 uploads in the last 24 h (the cap that blocked it), or if the
# episode is already queued or done. REQUEUE_DRY_RUN=1 runs the checks and enqueues nothing.
import datetime as dt
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from helios.config import file_roots, load_config
from helios.queue import QueueStore

JOB = "job_20261115_28a2bb55"
now = dt.datetime.now(dt.timezone.utc)
print("run", now.isoformat(timespec="seconds"))

c = Credentials.from_authorized_user_file(os.environ["YOUTUBE_TOKEN"])
c.refresh(Request())
yt = build("youtube", "v3", credentials=c, cache_discovery=False)
up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
items = yt.playlistItems().list(part="snippet", playlistId=up, maxResults=50).execute()["items"]
recent = sum(
    1 for i in items
    if (now - dt.datetime.fromisoformat(i["snippet"]["publishedAt"].replace("Z", "+00:00"))).total_seconds() < 86400
)
print("uploads in last 24 h:", recent)
if recent >= 10:
    print("SKIP: channel upload cap likely still reached")
    raise SystemExit(0)

qs = QueueStore(Path("/data"), file_roots=file_roots(load_config()))
old = qs.get_job(JOB)
live = [j.id for j in qs.list_jobs()
        if j.idempotency_key == old.idempotency_key and j.status in ("pending", "rendering", "awaiting_approval", "published")]
if live:
    print("SKIP: already queued or done:", live)
    raise SystemExit(0)
if os.environ.get("REQUEUE_DRY_RUN") == "1":
    print("DRY RUN: would enqueue", old.template, old.script_path, "privacy", old.youtube.get("privacy"))
    raise SystemExit(0)
job = qs.enqueue(template=old.template, vars=old.vars, youtube=old.youtube, idempotency_key=old.idempotency_key,
                 source=old.source, script_path=old.script_path, phase=old.phase)
print("ENQUEUED", job.id, job.status, job.youtube.get("privacy"))
