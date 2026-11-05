"""Multica as a seller of long skills on an AIMarket hub (idea 2, 2026-11-04; redesigned the same day).

A paid call on the hub cannot wait minutes for an agent, so a long skill is sold as two capabilities:

- ``github.digest.order@v1`` (paid) reads the public GitHub data at once, creates a task for a Multica agent
  through an autopilot webhook with that data in it, and answers with a ``job_id``;
- ``github.digest.result@v1`` (free) returns the job's state and, once ready, the digest.

Why this shape (the first live order, MY-62, failed on the earlier one):

- The service, not the agent, reads GitHub, with a token of its own that has no scopes. Unauthenticated reads
  share 60 requests an hour per host IP. Reading before the order is accepted also means a login that does not
  exist, or a GitHub outage, refuses the order, and the hub only charges for an answered call.
- The agent sends nothing over the network. Its final answer (one JSON line with a summary) is the
  deliverable; Multica posts it on the task, and this service reads it through a read-only database function
  that returns only the order agent's comments on the tasks its autopilot made for one job. An agent that reads
  outside text and then sends values from its own task is what WARDEN's flow guard refuses, rightly.
- The items (dated events with github.com links) are built here from GitHub's answer, so they cannot be
  made up. If the agent's summary is missing or malformed when the buyer reads after the timeout, or the
  agent's task ended without a usable answer, the service writes a plain summary from the same data: a paid
  order always gets its digest.

Only the buyer who ordered can read the result: the hub names its authenticated buyer to its operator's own
providers with ``X-AIMarket-Buyer-Ref`` (aimarket_hub/provider_buyer_ref.py), and a job is bound to that ref.
Buyer input never reaches the agent as free text: the order is a GitHub login that matches GitHub's own login
syntax and a number of days, both re-checked here.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, HTTPException, Request, Response

log = logging.getLogger("multica_provider")

LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
BUYER_REF = re.compile(r"bref-[0-9a-f]{32}")
JOB_ID = re.compile(r"job_[0-9a-f]{32}")
REPO = re.compile(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}")
URL = re.compile(r"https?://[^\s)\]>\"']+", re.I)
CONTROL = re.compile(r"[\x00-\x1f\x7f​-‏ -‮⁦-⁩]")
MAX_ITEMS = 50
MAX_REPOS = 10
MAX_SUMMARY = 2000
DONE_STATUSES = {"done", "cancelled", "blocked", "in_review"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Capability:
    product_id: str
    capability_id: str
    name: str
    description: str
    price_usd: float
    category: str
    input_schema: dict
    output_schema: dict


ORDER = Capability(
    "github-digest-order", "github.digest.order@v1", "Order a GitHub activity digest",
    "Order a digest of a GitHub user's or organization's public activity over the last 1-7 days. This call reads "
    "the public GitHub data at once and answers with a job_id; a Multica agent (OpenCode + DeepSeek) then writes "
    "the summary. Read the digest with github.digest.result@v1 (free) after about a minute, from the same buyer "
    "account. The order is refused, and not charged, if the login does not exist or GitHub cannot be read right "
    "now. If the agent has not written a usable summary within 20 minutes, the service writes a plain one from the "
    "same data, so a paid order always gets its digest. Needs a buyer the hub can name (credit account or "
    "verified payment).",
    0.05, "research/github",
    {"type": "object", "required": ["login"], "additionalProperties": False, "properties": {
        "login": {"type": "string", "pattern": "^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$",
                  "description": "GitHub user or organization login, e.g. octocat"},
        "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 7,
                 "description": "How many days back, 1 to 7"}}},
    {"type": "object", "properties": {
        "job_id": {"type": "string"}, "status": {"type": "string"}, "login": {"type": "string"},
        "days": {"type": "integer"}, "events_in_window": {"type": "integer"},
        "result_capability": {"type": "string"}, "poll_after_s": {"type": "integer"}}},
)
RESULT = Capability(
    "github-digest-result", "github.digest.result@v1", "Read a GitHub activity digest",
    "Read the state of a digest ordered with github.digest.order@v1 and, once ready, the digest itself: a short "
    "summary, up to 50 dated items with github.com links and the recently pushed repositories. summary_by says "
    "who wrote the summary (agent or service). Only the buyer account that placed the order can read it; results "
    "are kept for 7 days.",
    0.0, "research/github",
    {"type": "object", "required": ["job_id"], "additionalProperties": False, "properties": {
        "job_id": {"type": "string", "pattern": "^job_[0-9a-f]{32}$", "description": "job_id from the order"}}},
    {"type": "object", "properties": {
        "job_id": {"type": "string"}, "status": {"type": "string", "enum": ["queued", "done"]},
        "digest": {"type": "object"}, "summary_by": {"type": "string", "enum": ["agent", "service"]}}},
)
CAPABILITIES = {c.capability_id: c for c in (ORDER, RESULT)}


class Refused(Exception):
    """The order is refused before anything is created; the hub does not charge a refused call."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


class Signer:
    def __init__(self, key_file: str):
        path = Path(key_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self.key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        else:
            self.key = Ed25519PrivateKey.generate()
            pem = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption())
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(pem)

    @property
    def public_key(self) -> str:
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return base64.b64encode(raw).decode()

    def response_headers(self, capability_id: str, product_id: str, payload: dict, result: object) -> dict[str, str]:
        """The same signed binding memory-market sends (X-Provider-Signature over input hash and result)."""
        input_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        canonical = json.dumps({"capability_id": capability_id, "product_id": product_id,
                                "input_sha256": hashlib.sha256(input_json.encode()).hexdigest(), "result": result},
                               sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return {"X-Provider-Signature": base64.b64encode(self.key.sign(canonical.encode())).decode()}


class Jobs:
    """Orders, in a table of their own (``orders``; the first design's ``jobs`` table is left untouched)."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.execute("""create table if not exists orders (
                job_id text primary key, buyer_ref text not null, login text not null, days integer not null,
                data text not null, status text not null, created_at real not null, finished_at real,
                digest text, summary_by text)""")
            self.db.execute("create index if not exists orders_buyer on orders(buyer_ref, created_at)")
            self.db.commit()

    def create(self, buyer_ref: str, login: str, days: int, data: dict, now: float) -> str:
        job_id = "job_" + secrets.token_hex(16)
        with self.lock:
            self.db.execute("insert into orders values (?,?,?,?,?,?,?,?,?,?)",
                            (job_id, buyer_ref, login, days, json.dumps(data), "queued", now, None, None, None))
            self.db.commit()
        return job_id

    def delete(self, job_id: str) -> None:
        with self.lock:
            self.db.execute("delete from orders where job_id = ?", (job_id,))
            self.db.commit()

    def get(self, job_id: str) -> dict | None:
        keys = ("job_id", "buyer_ref", "login", "days", "data", "status", "created_at", "finished_at", "digest",
                "summary_by")
        with self.lock:
            row = self.db.execute(f"select {', '.join(keys)} from orders where job_id = ?", (job_id,)).fetchone()
        return dict(zip(keys, row)) if row else None

    def finish(self, job_id: str, digest: dict, summary_by: str, now: float) -> bool:
        with self.lock:
            cur = self.db.execute("update orders set status = 'done', digest = ?, summary_by = ?, finished_at = ? "
                                  "where job_id = ? and status = 'queued'",
                                  (json.dumps(digest), summary_by, now, job_id))
            self.db.commit()
            return cur.rowcount == 1

    def counts(self, buyer_ref: str, now: float, timeout_s: int) -> tuple[int, int, int]:
        day = now - 86400
        with self.lock:
            active = self.db.execute("select count(*) from orders where status = 'queued' and created_at >= ?",
                                     (now - timeout_s,)).fetchone()[0]
            today = self.db.execute("select count(*) from orders where created_at >= ?", (day,)).fetchone()[0]
            mine = self.db.execute("select count(*) from orders where buyer_ref = ? and created_at >= ?",
                                   (buyer_ref, day)).fetchone()[0]
        return active, today, mine

    def prune(self, now: float, retention_s: int) -> None:
        with self.lock:
            self.db.execute("delete from orders where created_at < ?", (now - retention_s,))
            self.db.commit()


def _clean(text: object, limit: int) -> str:
    value = CONTROL.sub(" ", str(text or ""))
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _github_url(candidate: object, repo: str) -> str:
    url = str(candidate or "")
    if url.startswith("https://github.com/") and not CONTROL.search(url) and " " not in url and len(url) <= 300:
        return url
    return f"https://github.com/{repo}"


def _item(event: dict) -> dict | None:
    repo = str((event.get("repo") or {}).get("name") or "")
    if not REPO.fullmatch(repo):
        return None
    kind, title, url = "other", _clean(event.get("type"), 60), f"https://github.com/{repo}"
    payload = event.get("payload") or {}
    etype = event.get("type")
    if etype == "PushEvent":
        branch = str(payload.get("ref") or "").removeprefix("refs/heads/")
        size = payload.get("size") or payload.get("distinct_size") or len(payload.get("commits") or [])
        kind = "push"
        title = f"pushed to {_clean(branch, 80) or 'a branch'}" + (f" ({size} commits)" if isinstance(size, int) and size > 1 else "")
    elif etype == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        number = payload.get("number") or pr.get("number")
        kind = "pr"
        title = f"{_clean(payload.get('action'), 20)} PR #{number}" + (f": {_clean(pr.get('title'), 120)}" if pr.get("title") else "")
        url = _github_url(pr.get("html_url"), f"{repo}/pull/{number}" if isinstance(number, int) else repo)
    elif etype in ("IssuesEvent", "IssueCommentEvent"):
        issue = payload.get("issue") or {}
        number = issue.get("number")
        kind = "issue"
        verb = "commented on" if etype == "IssueCommentEvent" else _clean(payload.get("action"), 20)
        title = f"{verb} #{number}" + (f": {_clean(issue.get('title'), 120)}" if issue.get("title") else "")
        url = _github_url(issue.get("html_url"), f"{repo}/issues/{number}" if isinstance(number, int) else repo)
    elif etype == "ReleaseEvent":
        release = payload.get("release") or {}
        kind = "release"
        title = f"released {_clean(release.get('name') or release.get('tag_name'), 100)}"
        url = _github_url(release.get("html_url"), repo)
    elif etype == "WatchEvent":
        kind, title = "star", "starred"
    elif etype == "ForkEvent":
        forkee = str((payload.get("forkee") or {}).get("full_name") or "")
        kind, title = "fork", f"forked to {forkee}" if REPO.fullmatch(forkee) else "forked"
    elif etype == "CreateEvent":
        kind = "create"
        title = f"created {_clean(payload.get('ref_type'), 20)} {_clean(payload.get('ref'), 80)}".strip()
    return {"repo": repo, "kind": kind, "title": _clean(title, 160), "url": url,
            "at": str(event.get("created_at") or "")[:10]}


def digest_data(user: dict, events: list, repos: list, days: int, now: float) -> dict:
    """What GitHub said, reduced to what a digest needs. Built here, so the items cannot be made up."""
    since = datetime.fromtimestamp(now - days * 86400, tz=timezone.utc)
    recent = []
    for event in events if isinstance(events, list) else []:
        try:
            at = datetime.fromisoformat(str(event.get("created_at")).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if at >= since:
            recent.append(event)
    items = [i for i in (_item(e) for e in recent) if i][:MAX_ITEMS]
    pushed = []
    for repo in repos if isinstance(repos, list) else []:
        name = str(repo.get("full_name") or "")
        if not REPO.fullmatch(name):
            continue
        pushed.append({"repo": name, "description": _clean(repo.get("description"), 200),
                       "language": _clean(repo.get("language"), 40), "stars": int(repo.get("stargazers_count") or 0),
                       "pushed": str(repo.get("pushed_at") or "")[:10]})
    return {"login": str(user.get("login")), "account_type": str(user.get("type")), "days": days,
            "since": since.strftime("%Y-%m-%d"), "events_in_window": len(recent), "items": items,
            "repos": pushed[:MAX_REPOS]}


def service_summary(data: dict) -> str:
    items = data.get("items") or []
    who = f"{data.get('login')} ({str(data.get('account_type') or 'account').lower()})"
    if not items:
        return f"{who} had no public GitHub activity in the last {data.get('days')} day(s)."
    kinds = Counter(i["kind"] for i in items)
    repos = Counter(i["repo"] for i in items)
    names = {"push": "pushes", "pr": "pull request events", "issue": "issue events", "release": "releases",
             "star": "stars", "fork": "forks", "create": "created refs", "other": "other events"}
    parts = ", ".join(f"{n} {names.get(k, k)}" for k, n in kinds.most_common())
    top = ", ".join(f"{r} ({n})" for r, n in repos.most_common(3))
    return (f"{who} had {data.get('events_in_window')} public GitHub events in the last {data.get('days')} day(s), "
            f"since {data.get('since')}: {parts}. Most active repositories: {top}.")


def parse_answer(content: object, job_id: str) -> str | None:
    """The agent's final answer: one JSON object {"job_id": ..., "summary": ...}. Anything else is not used."""
    text = str(content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        answer = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(answer, dict) or set(answer) - {"job_id", "summary"} or answer.get("job_id") != job_id:
        return None
    summary = answer.get("summary")
    if not isinstance(summary, str):
        return None
    summary = _clean(summary, MAX_SUMMARY + 1)
    if not summary or len(summary) > MAX_SUMMARY:
        return None
    if any(not u.startswith("https://github.com/") for u in URL.findall(summary)):
        return None
    return summary


def create_app(*, post_webhook=None, github_get=None, answers=None, clock=time.time) -> FastAPI:
    """``github_get(path) -> (status, json)``, ``answers(job_id) -> [{issue_status, content}]`` and
    ``post_webhook(payload)`` are injected in tests; the defaults talk to GitHub, Multica's database and Multica."""
    state: dict = {}

    def jobs() -> Jobs:
        if "jobs" not in state:
            state["jobs"] = Jobs(os.getenv("PROVIDER_DB", "/data/jobs.sqlite3"))
        return state["jobs"]

    def signer() -> Signer:
        if "signer" not in state:
            state["signer"] = Signer(os.getenv("PROVIDER_SIGNING_KEY_FILE", "/data/provider-signing-key.pem"))
        return state["signer"]

    async def default_post_webhook(payload: dict) -> None:
        # The autopilot's webhook URL carries its token: an env value from a 0600 env file, never logged.
        url = os.getenv("MULTICA_WEBHOOK_URL", "").strip()
        if not url:
            raise RuntimeError("MULTICA_WEBHOOK_URL is not configured")
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

    async def default_github_get(path: str) -> tuple[int, object]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "aicom-multica-provider/2 (+https://hub.attestedmemory.net)"}
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(base_url="https://api.github.com", timeout=6, follow_redirects=False,
                                     headers=headers) as client:
            response = await client.get(path)
            try:
                return response.status_code, response.json()
            except ValueError:
                return response.status_code, None

    def default_answers(job_id: str) -> list[dict]:
        import psycopg  # only the deployed service needs it

        with psycopg.connect(os.environ["MULTICA_DB_DSN"], connect_timeout=5, autocommit=True) as conn:
            rows = conn.execute("select issue_status, content from provider_ro.order_answers(%s)",
                                (job_id,)).fetchall()
        return [{"issue_status": r[0], "content": r[1]} for r in rows]

    send = post_webhook or default_post_webhook
    gh = github_get or default_github_get

    async def answers_for(job_id: str) -> list[dict]:
        if answers is not None:
            return answers(job_id)
        return await asyncio.to_thread(default_answers, job_id)

    async def read_github(login: str, days: int, now: float) -> dict:
        status, user = await gh(f"/users/{login}")
        if status == 404:
            raise Refused(422, "GitHub has no such login; nothing was ordered")
        if status in (403, 429):
            raise Refused(503, "GitHub's API limit is reached right now; nothing was ordered, try again later")
        if status != 200 or not isinstance(user, dict) or user.get("type") not in ("User", "Organization"):
            raise Refused(502, "GitHub could not be read right now; nothing was ordered")
        owner = "orgs" if user["type"] == "Organization" else "users"
        events_path = f"/{owner}/{login}/events" if owner == "orgs" else f"/users/{login}/events/public"
        (s1, events), (s2, repos) = await asyncio.gather(
            gh(f"{events_path}?per_page=100"), gh(f"/{owner}/{login}/repos?sort=pushed&per_page={MAX_REPOS}"))
        if s1 != 200 or s2 != 200:
            raise Refused(503 if 403 in (s1, s2) or 429 in (s1, s2) else 502,
                          "GitHub could not be read right now; nothing was ordered, try again later")
        return digest_data(user, events, repos, days, now)

    async def collect(job: dict, now: float) -> dict:
        """Take the agent's summary if it is there; otherwise, once the agent is done or time is up, the service's."""
        if job["status"] != "queued":
            return job
        data = json.loads(job["data"])
        rows: list[dict] = []
        try:
            rows = await answers_for(job["job_id"])
        except Exception as exc:  # noqa: BLE001 - a database hiccup only delays the agent's summary
            log.warning("answers unavailable for %s: %s", job["job_id"], type(exc).__name__)
        summary = None
        for row in reversed(rows):
            summary = parse_answer(row.get("content"), job["job_id"])
            if summary:
                break
        agent_finished = any(r.get("content") for r in rows) and \
            any(r.get("issue_status") in DONE_STATUSES for r in rows)
        timed_out = now - job["created_at"] >= _int("JOB_TIMEOUT_S", 1200)
        if summary is None and not (agent_finished or timed_out):
            return job
        digest = {"summary": summary or service_summary(data), "items": data["items"], "repos": data["repos"],
                  "login": data["login"], "account_type": data["account_type"], "days": data["days"],
                  "since": data["since"], "events_in_window": data["events_in_window"]}
        jobs().finish(job["job_id"], digest, "agent" if summary else "service", now)
        return jobs().get(job["job_id"]) or job

    def manifest(c: Capability) -> dict:
        base = os.getenv("AIMARKET_INVOKE_BASE", "http://multica-provider:8090").rstrip("/")
        publisher = os.getenv("AIMARKET_PUBLISHER_ID", "multica-provider")
        return {"product_id": c.product_id, "capability_id": c.capability_id, "name": c.name, "version": "v1",
                "description": c.description,
                "invoke_url": f"{base}/capabilities/{c.product_id}/{c.capability_id}/invoke",
                "price_per_call_usd": c.price_usd, "publisher": publisher, "publisher_id": publisher,
                "provider_pubkey": signer().public_key, "input_schema": c.input_schema,
                "output_schema": c.output_schema, "category": c.category,
                "p50_latency_ms": 1500 if c is ORDER else 60, "success_rate_30d": 0.95}

    async def register() -> int:
        hub, token = os.getenv("AIMARKET_HUB_URL", "").rstrip("/"), os.getenv("AIMARKET_PUBLISHER_TOKEN", "")
        if not hub or not token:
            return 0
        published = 0
        async with httpx.AsyncClient(timeout=10) as client:
            for c in (ORDER, RESULT):
                try:
                    r = await client.post(f"{hub}/ai-market/v2/supply/register", json=manifest(c),
                                          headers={"Authorization": f"Bearer {token}"})
                    r.raise_for_status()
                    published += 1
                except httpx.HTTPError as exc:
                    log.warning("registering %s failed: %s", c.capability_id, type(exc).__name__)
        log.info("registered %d of 2 capabilities", published)
        return published

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if os.getenv("PROVIDER_REQUIRE_TOKEN", "1") == "1" and len(os.getenv("AIMARKET_CAPABILITY_TOKEN", "")) < 32:
            raise RuntimeError("AIMARKET_CAPABILITY_TOKEN must be configured")
        jobs()
        signer()
        state["published"] = await register()
        yield

    app = FastAPI(title="Multica provider", lifespan=lifespan)

    def require_hub(request: Request) -> None:
        expected = os.getenv("AIMARKET_CAPABILITY_TOKEN", "").strip()
        supplied = request.headers.get("x-aimarket-internal-token", "")
        if len(expected) < 32 or not supplied or not hmac.compare_digest(expected, supplied):
            raise HTTPException(401, "capability gateway authentication required")

    def buyer(request: Request) -> str | None:
        ref = request.headers.get("x-aimarket-buyer-ref", "").strip()
        return ref if BUYER_REF.fullmatch(ref) else None

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "published": state.get("published", 0),
                "github_token": bool(os.getenv("GITHUB_TOKEN", "").strip())}

    @app.post("/capabilities/{product_id}/{capability_id}/invoke")
    async def invoke(product_id: str, capability_id: str, body: dict, request: Request, response: Response) -> dict:
        require_hub(request)
        c = CAPABILITIES.get(capability_id)
        if c is None or c.product_id != product_id:
            raise HTTPException(404, "unknown capability")
        payload = body.get("input", body)
        if not isinstance(payload, dict):
            raise HTTPException(422, "input must be an object")
        ref = buyer(request)
        if ref is None:
            raise HTTPException(403, "this capability needs a buyer the hub can name: call it with an X-API-Key "
                                     "credit account or a verified payment")
        now = clock()
        timeout_s = _int("JOB_TIMEOUT_S", 1200)
        jobs().prune(now, _int("RETENTION_DAYS", 7) * 86400)
        if c is ORDER:
            if set(payload) - {"login", "days"}:
                raise HTTPException(422, "only login and days are accepted")
            login, days = payload.get("login"), payload.get("days", 7)
            if not isinstance(login, str) or not LOGIN.fullmatch(login):
                raise HTTPException(422, "login must be a GitHub login (letters, digits, single hyphens)")
            if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 7:
                raise HTTPException(422, "days must be an integer from 1 to 7")
            active, today, mine = jobs().counts(ref, now, timeout_s)
            if active >= _int("MAX_ACTIVE_JOBS", 3) or today >= _int("MAX_JOBS_PER_DAY", 30) \
                    or mine >= _int("MAX_JOBS_PER_BUYER_DAY", 5):
                raise HTTPException(429, "too many digest orders right now; try again later")
            try:
                # The way back must work before anything is sold: an empty answer for a job that cannot exist.
                await answers_for("job_" + "0" * 32)
            except Exception as exc:  # noqa: BLE001
                log.warning("answers check failed: %s", type(exc).__name__)
                raise HTTPException(503, "the digest service is not available right now; nothing was ordered") from None
            try:
                data = await read_github(login, days, now)
            except Refused as refused:
                raise HTTPException(refused.status, refused.detail) from None
            except httpx.HTTPError:
                raise HTTPException(502, "GitHub could not be read right now; nothing was ordered") from None
            job_id = jobs().create(ref, data["login"], days, data, now)
            try:
                await send({"job_id": job_id, **data})
            except Exception:
                jobs().delete(job_id)
                raise HTTPException(502, "the agent queue is unavailable; nothing was ordered") from None
            result = {"job_id": job_id, "status": "queued", "login": data["login"], "days": days,
                      "events_in_window": data["events_in_window"], "result_capability": RESULT.capability_id,
                      "poll_after_s": 60}
        else:
            job_id = payload.get("job_id")
            job = jobs().get(job_id) if isinstance(job_id, str) and JOB_ID.fullmatch(job_id) else None
            if job is None or not hmac.compare_digest(job["buyer_ref"], ref):
                raise HTTPException(404, "no such job for this buyer")
            job = await collect(job, now)
            result = {"job_id": job_id, "status": job["status"], "login": job["login"], "days": job["days"]}
            if job["status"] == "done":
                result["digest"] = json.loads(job["digest"])
                result["summary_by"] = job["summary_by"]
            else:
                result["poll_after_s"] = 30
        for key, value in signer().response_headers(capability_id, product_id, payload, result).items():
            response.headers[key] = value
        return {"success": True, "result": result}

    return app


app = create_app()
