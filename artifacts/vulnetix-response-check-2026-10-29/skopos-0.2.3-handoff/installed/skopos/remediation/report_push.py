"""CONDUCTOR PUSH — telling SKOPOS how a remediation ended, over the fleet's own signed channel.

When a job reaches a terminal state the conductor summarises it and pushes that summary to
``POST /node/v1/report``: the same four headers, the same HMAC over the exact bytes on the wire, the
same claimed sequence number, signed with a credential an operator enrolled with a single-use ticket.
Nothing new listens anywhere — the conductor host stays outbound-only, exactly like every monitored
host. A second ingest surface, or a dashboard that polled the conductor, would hand the control plane
an inbound port it has no reason to have.

The body is the conductor's own document kind (``kind: remediation`` + a ``jobs`` list), which
``node_ingest`` routes to the remediation store before the log-report validator ever sees it. That
split is deliberate: teaching ``node_report`` about a remediation section would mean editing
``_DOC_KEYS`` and bumping ``PROTOCOL_VERSION``, and ``node_protocol.py`` ships byte-for-byte to every
monitored host — so a dashboard feature would have re-rolled all three deployed agents at once.

Three properties are worth stating plainly, because each is a bug rather than a preference:

**Best-effort, always.** A remediation that worked must never be recorded as failed because a
dashboard was down. An outage, a 401, a seq conflict, a timeout, a malformed answer: all logged, all
swallowed, and the return value is informational only. The job is already persisted by the time the
push is attempted, and nothing here is allowed to change it.

**A summary, never the job.** ``Job.ticket`` is the raw MOMUS ticket, kept verbatim and unbounded, and
the history notes interpolate MOMUS's ``detail`` and the Factory's error text — third-party,
log-injection-shaped content. So a fixed set of fields goes out, each scrubbed and length-capped, and
the ticket goes nowhere. Signatures travel as a truncated prefix: enough for a human to correlate one
against the order queue, useless as a credential. Verifying keys travel whole; they are public by
construction. Only the newest slice of the timeline is sent — the conductor's own ``jobs.jsonl``
remains the authority, and the pushed copy is a mirror.

**No endpoints, no addresses.** A target is identified by its component/service label, never by a URL
and never by an address. That is structural rather than a pattern match — the fields that could carry
one (the ``RemediationConfig``, the agent url, ``DeployOrder.host``, the node agent's own ``host``) are
simply never read. The shape filters below are the second line of defence, for free text someone else
wrote; a bare internal hostname has no shape to match on, which is exactly why the structural rule
comes first.

The sequence number is claimed and persisted BEFORE the request goes out, because the server claims it
during authentication — a number is spent even when the ingest afterwards fails. A pusher that only
advanced on success would keep retrying a number the server has already consumed and stay stuck on it
for ever. A 409 carries the number to use instead; it is adopted once, forward only, and by a sane
step, since that is the one value the far end gets to choose on this side.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from skopos.node_protocol import HDR_NODE, HDR_SEQ, HDR_SIGNATURE, HDR_TIMESTAMP, sign
from skopos.remediation.a2a_observer import scrub
from skopos.remediation.jobs import JobState

logger = logging.getLogger("skopos.remediation.push")

REPORT_PATH = "/node/v1/report"

#: What tells the receiver this is a board and not log lines — ``node_ingest.REMEDIATION_KIND``.
#: Spelled out rather than imported: ``node_ingest`` pulls in the dashboard's whole ingest stack (log
#: parsing, UA and GeoIP enrichment), none of which exists in the conductor's image.
REMEDIATION_KIND = "remediation"

#: Terminal states — the only ones that push. FAILED is here even though today's conductor always
#: converts an exhausted budget into ESCALATED: if a final-failed path is ever added, it must not
#: silently stop reporting.
TERMINAL_STATES = frozenset({JobState.DONE.value, JobState.FAILED.value, JobState.ESCALATED.value})

#: Who reported. Capped at 32 chars by the credential telemetry, and it names the conductor rather
#: than a host, so an operator can tell these pushes apart from a monitored host's.
PUSH_AGENT_VERSION = "skopos-conductor/1"

#: The newest N transitions. A job's history is unbounded over its life (every re-open appends), and
#: the tail is what an operator reads; the receiver keeps its own newest-window and sheds the timeline
#: entirely if a summary outgrows its storage budget, so staying well inside it is the point.
MAX_HISTORY_ENTRIES = 20

#: Free text — MOMUS's detail, the Factory's error, an agent's refusal reason. Same bound the A2A
#: observer uses, for the same reason.
TEXT_LIMIT = 240

#: A signature prefix long enough to match a record against the order queue by eye. The board already
#: truncates key material at about this width.
SIG_PREFIX = 20

#: Matches the reference pusher: below this, compressing costs more than it saves.
GZIP_THRESHOLD_BYTES = 64 * 1024

#: How far a 409's ``next_seq`` may move this counter in one step. Same bound as the node agent.
MAX_ADOPT_STEP = 100_000


@dataclass
class PushConfig:
    """Where to push and what to sign with. Empty = the push is off."""

    base_url: str = ""
    key_id: str = ""
    secret_b64: str = ""
    #: Enrollment's own artefact (``{"key_id", "secret_b64", "server_name"}``), so the secret can stay
    #: in a mounted file instead of the conductor's environment. Same variable and same file the node
    #: agent reads (``SKOPOS_NODE_CREDENTIAL``), because it is the same enrollment.
    credential_path: str = ""
    state_path: str = ""
    ca_file: str = ""
    allow_plaintext: bool = False
    #: Short on purpose: this runs on a job's terminal transition, and a dashboard's TCP timeout is
    #: not a reason to hold a remediation open.
    timeout_s: float = 10.0

    @classmethod
    def from_env(cls, data_dir: str = "") -> "PushConfig":
        d = data_dir or os.environ.get("SKOPOS_REMEDIATION_DIR", "data/remediation")
        return cls(
            base_url=os.environ.get("SKOPOS_REPORT_URL", "").strip(),
            key_id=os.environ.get("SKOPOS_NODE_KEY_ID", "").strip(),
            secret_b64=os.environ.get("SKOPOS_NODE_SECRET_B64", "").strip(),
            credential_path=os.environ.get("SKOPOS_NODE_CREDENTIAL", "").strip(),
            state_path=os.path.join(d, "report_push_state.json"),
            ca_file=os.environ.get("SKOPOS_REPORT_CA_FILE", "").strip(),
            allow_plaintext=os.environ.get("SKOPOS_REPORT_ALLOW_PLAINTEXT", "").strip().lower()
            in ("1", "true", "yes"),
            # A typo in a tuning knob must not stop the conductor from starting.
            timeout_s=_env_float("SKOPOS_REPORT_TIMEOUT_S", 10.0),
        )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        logger.warning("%s is not a number; using %s", name, default)
        return default


# ── redaction ───────────────────────────────────────────────────────────────────
#
# Applied to values *before* they are serialised, never after: a filter that runs on the finished JSON
# has already had to guess where the field boundaries are.

_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s\"'<>]+")
_IPV4 = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])")
#: An IPv6 literal is recognised by a ``::`` run or by four-plus hextets. Requiring one of those is
#: what keeps ``12:00:00`` in a timestamp from being read as an address and mangled.
_IPV6 = re.compile(
    r"(?<![\w:])(?=[0-9a-fA-F:]*::|(?:[0-9a-fA-F]{0,4}:){3})"
    r"[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){1,7}(?![\w:])"
)
#: ``host:port`` — a colon and a port is the strongest shape signal that a word is an endpoint.
_HOST_PORT = re.compile(r"(?<![\w.\-])(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,24}:\d{1,5}\b")
#: ``Authorization: Bearer <blob>``. The shared scrubber's ``name=value`` rule stops at the scheme
#: word and leaves the credential itself sitting there, which is the one shape a quoted HTTP header
#: arrives in.
_BEARER = re.compile(r"(?i)\b(bearer|basic|token)\s+[A-Za-z0-9._\-+/=]{8,}")


def redact(value: Any, *, limit: int = TEXT_LIMIT) -> str:
    """Make one third-party string safe to publish to a dashboard.

    ``scrub`` already removes control characters, rewrites ``token=…``-shaped pairs and bounds the
    length. This adds the location filters, because a URL or an address in a MOMUS detail line is how
    a private host ends up rendered to everyone who can see the dashboard.
    """
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = _URL.sub("<url>", text)
    text = _HOST_PORT.sub("<host>", text)
    text = _IPV6.sub("<ip>", text)
    text = _IPV4.sub("<ip>", text)
    text = _BEARER.sub(r"\1 <redacted>", text)
    return scrub(text, limit=limit)


def label(value: Any, *, limit: int = 96) -> str:
    """A short field the conductor produced itself: bounded and stripped, not location-filtered.

    Timestamps, states and key material live here. Running the address filters over
    ``2026-08-08T12:00:00Z`` would be a rewrite with no threat behind it.
    """
    return scrub("" if value is None else str(value), limit=limit)


def redact_image(value: Any) -> str:
    """An image ref, minus its registry.

    ``registry.internal:5000/oracles:patched`` names a private host in its first segment; the part an
    operator actually reads is the repository and the tag.
    """
    text = label(value, limit=TEXT_LIMIT)
    head, sep, rest = text.partition("/")
    if sep and ("." in head or ":" in head):
        return f"<registry>/{rest}"
    return text


def _signature_prefix(container: Any) -> str:
    """The signature's value, truncated. Never the envelope around it."""
    if isinstance(container, dict):
        container = container.get("value")
    return label(container, limit=SIG_PREFIX)


def _verdict(raw: Any) -> dict[str, Any]:
    """One MOMUS FixVerdict, flattened to the fields the board reads."""
    if not isinstance(raw, dict) or not raw:
        return {}
    return {
        "fixed": bool(raw.get("fixed")),
        "outcome": label(raw.get("outcome"), limit=32),
        "detail": redact(raw.get("detail") or ""),
        "checked_at": label(raw.get("checked_at"), limit=32),
        # Public keys go whole — they are what a reader checks a signature against.
        "verifier_pubkey": label(raw.get("verifier_pubkey"), limit=128),
        "signature": _signature_prefix(raw.get("signature")),
    }


def job_summary(
    job: Any, *, conductor_pubkey: str = "", queued: dict[str, Any] | None = None
) -> dict[str, Any]:
    """One terminal job as the pushed summary.

    ``queued`` is the order-queue record for this job's deploy order (``QueuedOrder.to_dict()``). The
    signed order, its claim and what the node agent actually did are not on the ``Job`` at all, so the
    caller joins them in — and ``host`` is dropped on the way through, because on our fleet it repeats
    the component label and on someone else's it is an address.
    """
    ticket = getattr(job, "ticket", None) or {}
    result = getattr(job, "result", None) or {}
    queued = queued or {}
    order = queued.get("order") or {}

    history = [
        {
            "ts": label(entry.get("ts"), limit=32),
            "state": label(entry.get("state"), limit=32),
            # The notes are the timeline copy an operator reads, and the one place MOMUS's and the
            # Factory's own text ends up.
            "note": redact(entry.get("note") or ""),
        }
        for entry in list(getattr(job, "history", None) or [])[-MAX_HISTORY_ENTRIES:]
        if isinstance(entry, dict)
    ]

    summary: dict[str, Any] = {
        "finding_id": redact(getattr(job, "finding_id", ""), limit=96),
        "component": redact(getattr(job, "component", ""), limit=96),
        # MOMUS's target label. It rides on the ticket and the verdict, never on the Job.
        "target": redact(ticket.get("target") or ticket.get("target_kind") or "", limit=96),
        "probe": redact(getattr(job, "probe", ""), limit=96),
        "severity": redact(getattr(job, "severity", ""), limit=32),
        "route": label(getattr(job, "route", ""), limit=32),
        "state": label(getattr(job, "state", ""), limit=32),
        "attempts": int(getattr(job, "attempts", 0) or 0),
        "created_at": label(getattr(job, "created_at", ""), limit=32),
        "updated_at": label(getattr(job, "updated_at", ""), limit=32),
        "history": history,
    }

    gate = _verdict(result.get("gate_verdict"))
    if gate:
        summary["gate_verdict"] = gate
    post = _verdict(result.get("post_deploy_verdict"))
    if post:
        summary["post_deploy_verdict"] = post

    order_id = label(result.get("deploy_order_id") or order.get("order_id"), limit=128)
    deploy: dict[str, Any] = {}
    if order_id:
        deploy["order_id"] = order_id
    if order:
        deploy.update({
            "service": redact(order.get("service") or "", limit=96),
            "image": redact_image(order.get("image") or ""),
            "created_at": label(order.get("created_at"), limit=32),
            "signature": _signature_prefix(order.get("signature")),
        })
    # The conductor's own verifying key belongs in this section: it is where the board reads it from,
    # and it is what says which conductor signed — so it is sent even when nothing was deployed.
    pubkey = label(conductor_pubkey or order.get("conductor_pubkey"), limit=128)
    if pubkey:
        deploy["conductor_pubkey"] = pubkey
    if deploy:
        summary["deploy"] = deploy

    if queued:
        summary["queue"] = {
            "state": label(queued.get("state"), limit=32),
            # An agent id, which on a foreign fleet may be a host — held to the same filters.
            "claimed_by": redact(queued.get("claimed_by") or "", limit=96),
            "claimed_at": label(queued.get("claimed_at"), limit=32),
        }

    agent_result = queued.get("result")
    if isinstance(agent_result, dict) and agent_result:
        summary["agent_result"] = {
            "deployed": bool(agent_result.get("deployed")),
            "refused": bool(agent_result.get("refused")),
            "reason": redact(agent_result.get("reason") or ""),
            "executed_at": label(agent_result.get("executed_at"), limit=32),
        }
    return summary


def build_document(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """The pushed envelope. ``kind`` is what routes it away from the log-report validator."""
    return {
        "kind": REMEDIATION_KIND,
        "agent_version": PUSH_AGENT_VERSION,
        "generated_at": int(time.time()),
        "jobs": summaries,
    }


class _SeqTaken(Exception):
    """A 409: the number was spent by an earlier attempt. Carries the one to use instead."""

    def __init__(self, next_seq: int):
        super().__init__(f"sequence number already used; next is {next_seq}")
        self.next_seq = next_seq


class PushRefused(Exception):
    """The push was not attempted because doing so would be unsafe (e.g. a plaintext base_url)."""


class ReportPusher:
    """Pushes terminal-job summaries to SKOPOS. Never raises, never blocks a job.

    ``opener`` is a seam for tests: anything with ``.open(request, timeout=…)``. In production it is an
    opener with an EMPTY ``ProxyHandler``, so an ``HTTPS_PROXY`` in the environment cannot become a man
    in the middle for the fleet's control-plane traffic.
    """

    def __init__(self, config: PushConfig | None = None, *, data_dir: str = "", opener: Any = None):
        self.cfg = config or PushConfig.from_env(data_dir)
        self._opener = opener

    # ── configuration ───────────────────────────────────────────────────────
    def _credential(self) -> tuple[str, bytes] | None:
        """(key_id, raw secret), or None if the conductor is not enrolled.

        Read per push rather than cached, so a rotated credential is picked up without a restart. The
        secret is base64 in the enrollment answer and raw bytes in the signature; decoding it in one
        place is what stops the classic "well-formed signature that always 401s".
        """
        key_id, secret_b64 = self.cfg.key_id, self.cfg.secret_b64
        if not (key_id and secret_b64) and self.cfg.credential_path:
            try:
                with open(self.cfg.credential_path, "r", encoding="utf-8") as fh:
                    doc = json.load(fh)
                key_id = key_id or str(doc.get("key_id") or "").strip()
                secret_b64 = secret_b64 or str(doc.get("secret_b64") or doc.get("secret") or "").strip()
            except (OSError, ValueError) as exc:
                logger.warning("cannot read the node credential: %s", type(exc).__name__)
                return None
        if not key_id or not secret_b64:
            return None
        try:
            return key_id, base64.b64decode(secret_b64)
        except (ValueError, TypeError):
            logger.warning("the node secret is not valid base64; refusing to sign with it")
            return None

    @property
    def configured(self) -> bool:
        """Opt-in: a url AND a credential. Anything less is a silent no-op, not an error."""
        return bool(self.cfg.base_url) and self._credential() is not None

    # ── sequence state ──────────────────────────────────────────────────────
    def _load_state(self) -> dict[str, Any]:
        try:
            with open(self.cfg.state_path, "r", encoding="utf-8") as fh:
                state = json.load(fh)
            return state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            # A missing or unreadable counter starts over at 1 and the server's 409 resync walks it
            # back to where it should be — which is why this is not a failure.
            return {}

    def _claim_seq(self, explicit: int | None = None) -> int | None:
        """Take the next number and persist it BEFORE it is used. See the module docstring.

        None when the counter could not be written: a number we failed to record must not be used, or
        a crash right after this would re-spend it on the next run.
        """
        state = self._load_state()
        current = int(state.get("seq", 0) or 0)
        seq = current + 1 if explicit is None else int(explicit)
        state["seq"] = seq
        tmp = f"{self.cfg.state_path}.tmp"
        try:
            os.makedirs(os.path.dirname(self.cfg.state_path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(state, fh)
            # A half-written counter is not a state worth having.
            os.replace(tmp, self.cfg.state_path)
        except OSError as exc:
            logger.warning("cannot record the push sequence number: %s", exc)
            return None
        return seq

    def _adopt_seq(self, next_seq: int) -> int | None:
        current = int(self._load_state().get("seq", 0) or 0)
        # Forward only, and only by a sane step: this is the one value the far end influences here.
        if not current < next_seq <= current + MAX_ADOPT_STEP:
            logger.warning("SKOPOS proposed seq %s, which is not a sane step from %s", next_seq, current)
            return None
        return self._claim_seq(next_seq)

    # ── the push ────────────────────────────────────────────────────────────
    def push_job(
        self, job: Any, *, conductor_pubkey: str = "", queued: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Summarise a terminal job and push it. Returns a report; never raises."""
        state = str(getattr(job, "state", ""))
        if state not in TERMINAL_STATES:
            # Pushing every transition would spend the fleet's two shared ingest slots on a dashboard.
            return {"pushed": False, "reason": f"not a terminal state ({state})"}
        credential = self._credential()
        if not self.cfg.base_url or credential is None:
            return {"pushed": False, "reason": "not configured"}
        key_id, secret = credential

        try:
            summary = job_summary(job, conductor_pubkey=conductor_pubkey, queued=queued)
            body, extra_headers = _encode(build_document([summary]))
        except Exception as exc:  # noqa: BLE001 - a summary we cannot build is not a failed remediation
            logger.warning("could not build the terminal-state summary: %s", type(exc).__name__)
            return {"pushed": False, "reason": f"summary error: {type(exc).__name__}"}

        seq = self._claim_seq()
        # One retry, and only for a seq conflict: a conflict means an earlier attempt of ours was
        # authenticated and then failed, so the number is spent and SKOPOS has told us the next one.
        for attempt in (1, 2):
            if seq is None:
                break
            try:
                answer = self._send(body, extra_headers, key_id=key_id, secret=secret, seq=seq)
                return {"pushed": True, "seq": seq, "server": answer}
            except _SeqTaken as taken:
                if attempt == 2:
                    # Give up on this summary, but still take the number: the next terminal job
                    # should not be born already stuck behind the same conflict.
                    self._adopt_seq(taken.next_seq)
                    logger.warning("terminal-state push kept losing the seq race; giving up")
                    return {"pushed": False, "reason": "seq conflict", "next_seq": taken.next_seq}
                seq = self._adopt_seq(taken.next_seq)
            except PushRefused as exc:
                logger.warning("terminal-state push refused: %s", exc)
                return {"pushed": False, "reason": str(exc)}
            except Exception as exc:  # noqa: BLE001 - the whole point: a dashboard cannot fail a job
                # Includes a 401, which by design says nothing more than "unauthorized": on this
                # channel that means not enrolled, wrong secret, revoked, a skewed clock or a seq
                # jump, and only the conductor's own log will ever say which.
                logger.warning(
                    "terminal-state push failed (%s: %s) — the job outcome stands",
                    type(exc).__name__, exc,
                )
                return {"pushed": False, "reason": f"{type(exc).__name__}: {exc}"}
        return {"pushed": False, "reason": "seq conflict"}

    async def push_job_async(self, job: Any, **kwargs: Any) -> dict[str, Any]:
        """``push_job`` off the event loop, so a slow dashboard cannot stall the conductor."""
        if not self.cfg.base_url:
            return {"pushed": False, "reason": "not configured"}
        try:
            return await asyncio.to_thread(self.push_job, job, **kwargs)
        except Exception as exc:  # noqa: BLE001 - not even a broken pusher may change an outcome
            logger.warning("terminal-state push could not run: %s", type(exc).__name__)
            return {"pushed": False, "reason": f"push error: {type(exc).__name__}"}

    # ── transport ───────────────────────────────────────────────────────────
    def _send(
        self,
        body: bytes,
        extra_headers: dict[str, str],
        *,
        key_id: str,
        secret: bytes,
        seq: int,
    ) -> dict[str, Any]:
        base = self.cfg.base_url.rstrip("/")
        if not base.startswith("https://") and not self.cfg.allow_plaintext:
            raise PushRefused("report url must be https (set SKOPOS_REPORT_ALLOW_PLAINTEXT for a lab)")
        timestamp = int(time.time())
        headers = {"Content-Type": "application/json", **extra_headers}
        headers.update(
            {
                HDR_NODE: key_id,
                HDR_TIMESTAMP: str(timestamp),
                HDR_SEQ: str(seq),
                # The shared protocol module, not a local copy: signing and verification must be one
                # implementation over the exact bytes on the wire (after gzip, before anything else).
                HDR_SIGNATURE: sign(secret, key_id=key_id, timestamp=timestamp, seq=seq, body=body),
            }
        )
        request = urllib.request.Request(base + REPORT_PATH, data=body, headers=headers, method="POST")
        try:
            with self._get_opener().open(request, timeout=self.cfg.timeout_s) as response:
                return json.loads(response.read(65536).decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            if exc.code != 409:
                raise
            try:
                hint = json.loads(exc.read(4096).decode("utf-8") or "{}")
                raise _SeqTaken(int(hint["next_seq"])) from None
            except (ValueError, KeyError, TypeError):
                raise exc from None

    def _get_opener(self) -> Any:
        if self._opener is None:
            import ssl

            context = ssl.create_default_context()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            if self.cfg.ca_file and os.path.isfile(self.cfg.ca_file):
                context.load_verify_locations(self.cfg.ca_file)
            self._opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=context),
            )
        return self._opener


def _encode(doc: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    """Serialise deterministically, and gzip only when it is worth it.

    The signature covers whatever comes back from here, so compression has to happen before signing and
    never again afterwards.
    """
    body = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(body) > GZIP_THRESHOLD_BYTES:
        return gzip.compress(body, 6), {"Content-Encoding": "gzip"}
    return body, {}
