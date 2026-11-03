"""Whether a capability's answer depends on what it was asked.

A listing that answers every request with one and the same document (an install pack, a brochure, a list of
where else to buy) is a handout, not a service. The owner's rule (2026-10-06): search keeps it, because it may
be exactly what somebody wants, but ranks it after every capability whose answer is computed from the request.
Demoted, never removed.

Measured, never declared. For each successful answer the hub routes, it keeps a digest of the input and a
digest of the answer (never the input itself). A capability is input-independent when, within the last 30
days, it gave one and the same answer to at least two different inputs, and gave it again at least a day after
it first did. Each condition stops an honest service from being caught:

  * the day: a live-data service whose parameters are all optional ("gas price", default chain) answers two
    meaningless inputs alike within one block. It does not answer alike a day later; a handout does.
  * the size floor: a balance service gives two empty wallets the same tiny answer. A handout is a document.
  * error answers are never recorded: two "address required" replies say nothing about the service.

Coverage does not wait for traffic. During each crawl cycle the hub asks a few FREE federated capabilities
itself, with inputs no real service can act on, and records the answers the same way (`probe_free`). It never
probes a paid capability (that spends money), nor one whose name says it acts (send, pay, create, cancel, run):
a probe must not be able to do anything. A local capability served from a static pack (a JSON object in
prompt_template and no invoke_url) returns that object for every input by construction, so it needs no calls.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import re
import secrets
import time
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

WINDOW_S = 30 * 86400          # observations older than this no longer count
SPAN_S = 24 * 3600             # the same answer must come back at least this much later
MIN_ANSWER_BYTES = 200         # below this an identical answer is an empty result, not a document
KEEP_INPUTS = 8                # distinct inputs remembered per capability
PROBE_EVERY_S = 7 * 86400      # how often a free capability is asked again
PROBE_LIMIT = 8                # capabilities probed per crawl cycle
PROBE_TIMEOUT_S = 20.0

# Words in an id or name that say the capability does something. A probe of such a capability could do it.
_ACTING = frozenset({
    "send", "post", "create", "cancel", "delete", "remove", "write", "transfer", "pay", "payment", "publish",
    "mint", "deploy", "register", "update", "set", "submit", "order", "buy", "sell", "execute", "run", "trigger",
    "start", "stop", "approve", "sign", "swap", "bridge", "withdraw", "deposit", "invoice", "refund", "notify",
    "email", "sms", "message", "subscribe", "unsubscribe", "book", "schedule", "upload", "store", "save", "vote",
    "claim", "stake", "unstake", "lock", "unlock", "burn", "issue", "revoke", "reset", "kill", "spawn",
})
_WORD = re.compile(r"[a-z0-9]+")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._@:-]{1,80}$")

Key = tuple[str, str, str]  # (source_hub, product_id, capability_id)


def key_of(capability: Any) -> Key:
    return (
        str(getattr(capability, "source_hub", "") or "local"),
        str(getattr(capability, "product_id", "") or ""),
        str(getattr(capability, "capability_id", "") or ""),
    )


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def answer_of(response: Any) -> Any:
    """The answer inside a routed response: a hub envelope's `result`, otherwise the body itself."""
    if isinstance(response, dict) and "result" in response:
        return response.get("result")
    return response


def is_error(response: Any, answer: Any) -> bool:
    """An error, a refusal or nothing at all: none of them says whether the answer depends on the input."""
    if answer is None or answer in ("", {}, []):
        return True
    for doc in (response, answer):
        if not isinstance(doc, dict):
            continue
        if doc.get("success") is False or doc.get("ok") is False:
            return True
        if doc.get("error") or doc.get("errors"):
            return True
        if str(doc.get("status") or "").strip().lower() in {"error", "failed", "failure", "fail"}:
            return True
    return False


def is_static_pack(capability: Any) -> bool:
    """A local capability whose answer is a stored JSON object, returned verbatim whatever the input."""
    return (
        str(getattr(capability, "source_hub", "") or "local") == "local"
        and not str(getattr(capability, "invoke_url", "") or "").strip()
        and str(getattr(capability, "prompt_template", "") or "").strip().startswith("{")
    )


def acts(capability: Any) -> bool:
    """Whether the capability's own id or name says it does something a probe must not trigger."""
    text = " ".join(
        str(getattr(capability, field, "") or "") for field in ("capability_id", "product_id", "name")
    ).lower()
    return bool(set(_WORD.findall(text)) & _ACTING)


def project(request_input: Any, schema: Any) -> Any:
    """The part of an input the capability declares it reads.

    The digest used to be over the caller's whole input, so anyone could mint "different
    inputs" by adding fields the capability ignores: the same answer N times then marked a
    perfectly input-dependent competitor as a handout and pushed it down search. Fields the
    input_schema does not name are dropped before hashing; with no usable schema the input
    is kept as is.
    """
    if not isinstance(request_input, dict) or not isinstance(schema, dict):
        return request_input
    props = schema.get("properties")
    if not isinstance(props, dict) or not props:
        return request_input
    return {k: v for k, v in request_input.items() if k in props}


def _schema_for(db: Any, key: Key) -> Any:
    getter = getattr(db, "get_capability", None)
    if getter is None:
        return None
    try:
        cap = getter(key[1], key[2], key[0])
    except Exception:  # noqa: BLE001 - a ranking hint never fails a call
        return None
    return getattr(cap, "input_schema", None) if cap is not None else None


def observe(db: Any, key: Key, request_input: Any, response: Any, *, now: float | None = None) -> bool:
    """Record one answer. Returns False, recording nothing, for an error or an empty answer."""
    answer = answer_of(response)
    if is_error(response, answer):
        return False
    request_input = project(request_input, _schema_for(db, key))
    stamp = time.time() if now is None else now
    body = canonical(answer).encode("utf-8")
    conn = db._conn
    conn.execute(
        "INSERT INTO answer_observations (source_hub, product_id, capability_id, input_digest, "
        "answer_digest, answer_bytes, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (source_hub, product_id, capability_id, input_digest) DO UPDATE SET "
        "first_seen = CASE WHEN answer_observations.answer_digest = excluded.answer_digest "
        "THEN answer_observations.first_seen ELSE excluded.first_seen END, "
        "answer_digest = excluded.answer_digest, answer_bytes = excluded.answer_bytes, "
        "last_seen = excluded.last_seen",
        (*key, digest(request_input), hashlib.sha256(body).hexdigest(), len(body), stamp, stamp),
    )
    conn.execute(
        "DELETE FROM answer_observations WHERE source_hub = ? AND product_id = ? AND capability_id = ? "
        "AND input_digest NOT IN (SELECT input_digest FROM answer_observations "
        "WHERE source_hub = ? AND product_id = ? AND capability_id = ? ORDER BY last_seen DESC LIMIT ?)",
        (*key, *key, KEEP_INPUTS),
    )
    conn.commit()
    return True


def independent_keys(db: Any, *, now: float | None = None) -> set[Key]:
    """Every capability whose observed answers show it does not depend on its input."""
    since = (time.time() if now is None else now) - WINDOW_S
    try:
        rows = db._conn.execute(
            "SELECT source_hub, product_id, capability_id FROM answer_observations WHERE last_seen >= ? "
            "GROUP BY source_hub, product_id, capability_id "
            "HAVING COUNT(*) >= 2 AND COUNT(DISTINCT answer_digest) = 1 AND MIN(answer_bytes) >= ? "
            "AND MAX(last_seen) - MIN(first_seen) >= ?",
            (since, MIN_ANSWER_BYTES, SPAN_S),
        ).fetchall()
    except Exception as exc:  # search must never fail over a ranking hint
        logger.warning("answer dependence: could not read observations: %s", exc)
        return set()
    keys = set()
    for row in rows:
        r = dict(row)
        keys.add((str(r["source_hub"]), str(r["product_id"]), str(r["capability_id"])))
    return keys


def demote(matches: list, independent: set[Key]) -> list:
    """Every match whose answer depends on its input first, then the rest, each group in its own order.

    The demoted ones stay in the list and say why (`input_independent`).
    """
    head, tail = [], []
    for match in matches:
        cap = match.capability
        if key_of(cap) in independent or is_static_pack(cap):
            tail.append(dataclasses.replace(match, input_independent=True))
        else:
            head.append(match)
    return head + tail


# ── Probing free federated capabilities ─────────────────────────────────────────────────────────────────────


def probing_enabled() -> bool:
    return (os.environ.get("AIMARKET_ANSWER_PROBE") or "1").strip().lower() not in {"0", "false", "no", "off"}


def _is_free(capability: Any) -> bool:
    routed = getattr(capability, "routed_price_usd", None)
    try:
        return float(getattr(capability, "price_per_call_usd", 0) or 0) <= 0 and float(routed or 0) <= 0
    except (TypeError, ValueError):
        return False


def _probe_state(db: Any, key: Key) -> tuple[float | None, int, int]:
    """(last probe time, distinct inputs, distinct answers) for one capability."""
    row = db._conn.execute(
        "SELECT probed_at FROM answer_probes WHERE source_hub = ? AND product_id = ? AND capability_id = ?",
        key,
    ).fetchone()
    probed_at = float(dict(row)["probed_at"]) if row is not None else None
    seen = db._conn.execute(
        "SELECT COUNT(*) AS inputs, COUNT(DISTINCT answer_digest) AS answers FROM answer_observations "
        "WHERE source_hub = ? AND product_id = ? AND capability_id = ?",
        key,
    ).fetchone()
    s = dict(seen) if seen is not None else {}
    return probed_at, int(s.get("inputs") or 0), int(s.get("answers") or 0)


def probe_candidates(db: Any, *, now: float | None = None, limit: int = PROBE_LIMIT) -> list:
    """Free federated capabilities due for a probe, confirmations of a suspected handout first."""
    from aimarket_hub.access_policy import capability_is_publicly_offerable
    from aimarket_hub.fulfillment import capability_is_fulfillable

    stamp = time.time() if now is None else now
    due: list[tuple[int, float, Any]] = []
    for cap in db.list_capabilities(limit=None):
        if key_of(cap)[0] == "local" or getattr(cap, "is_demo", False) or not _is_free(cap) or acts(cap):
            continue
        if not (capability_is_fulfillable(cap) and capability_is_publicly_offerable(cap)):
            continue
        probed_at, inputs, answers = _probe_state(db, key_of(cap))
        if probed_at is None:
            due.append((1, 0.0, cap))
        elif inputs >= 2 and answers == 1 and stamp - probed_at >= SPAN_S:
            due.append((0, probed_at, cap))   # one identical answer so far: ask again a day later
        elif stamp - probed_at >= PROBE_EVERY_S:
            due.append((2, probed_at, cap))
    due.sort(key=lambda item: (item[0], item[1]))
    return [cap for _priority, _at, cap in due[:max(0, limit)]]


def _visitor(config: Any) -> str:
    # The same visitor a routed free call sends (api.py), so a peer sees one hub, not two.
    return (os.environ.get("AIMARKET_FEDERATION_VISITOR") or "").strip() or (
        "hub-fed-" + hashlib.sha256((getattr(config, "hub_url", "") or "hub").encode()).hexdigest()[:20]
    )


async def _ask(capability: Any, peer: Any, endpoint: str | None, value: dict, *, post: Callable[..., Awaitable[Any]],
               config: Any) -> Any:
    headers = {"X-AIMarket-Probe": "answer-dependence", "X-AIMarket-Sandbox-Visitor": _visitor(config)}
    try:
        if endpoint:
            to_hub = endpoint.rstrip("/").endswith("/ai-market/v2/invoke")
            resp = await post(endpoint, json={
                "capability_id": capability.capability_id,
                "input": value,
                "product_id": capability.product_id,
                "source_hub": "local" if to_hub else getattr(config, "hub_url", ""),
            }, headers=headers, timeout=PROBE_TIMEOUT_S)
        else:
            if not (_SAFE_ID.match(capability.product_id) and _SAFE_ID.match(capability.capability_id)):
                return None
            if ".." in capability.product_id or ".." in capability.capability_id:
                return None
            base = str(getattr(peer, "url", "") or "").rstrip("/")
            resp = await post(f"{base}/capabilities/{capability.product_id}/{capability.capability_id}/invoke",
                              json=value, headers=headers, timeout=PROBE_TIMEOUT_S)
    except Exception as exc:
        logger.debug("answer probe of %s failed: %s", capability.capability_id, exc)
        return None
    if getattr(resp, "status_code", 0) != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


async def probe_free(db: Any, config: Any, *, resolve_endpoint: Callable[[Any], Awaitable[str | None]],
                     post: Callable[..., Awaitable[Any]], now: float | None = None,
                     limit: int = PROBE_LIMIT) -> dict:
    """Ask the free federated capabilities that are due, record what they answer. Never raises."""
    if not probing_enabled():
        return {"probed": 0, "disabled": True}
    stamp = time.time() if now is None else now
    stats = {"probed": 0, "answers": 0}
    try:
        candidates = probe_candidates(db, now=stamp, limit=limit)
    except Exception as exc:
        logger.warning("answer probe: could not choose candidates: %s", exc)
        return stats
    for cap in candidates:
        key = key_of(cap)
        try:
            peer = db.get_peer(key[0])
            if peer is None:
                continue
            endpoint = await resolve_endpoint(peer)
            first = _probe_state(db, key)[0] is None
            answered = 0
            # Inputs nothing can act on, different every time: a service has to error or answer each
            # on its merits; a handout answers them all with itself.
            for _ in range(2 if first else 1):
                value = {"probe": secrets.token_hex(8)}
                response = await _ask(cap, peer, endpoint, value, post=post, config=config)
                if response is not None and observe(db, key, value, response, now=stamp):
                    answered += 1
            db._conn.execute(
                "INSERT INTO answer_probes (source_hub, product_id, capability_id, probed_at, answered) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (source_hub, product_id, capability_id) DO UPDATE SET "
                "probed_at = excluded.probed_at, answered = excluded.answered",
                (*key, stamp, answered),
            )
            db._conn.commit()
            stats["probed"] += 1
            stats["answers"] += answered
        except Exception as exc:
            logger.warning("answer probe of %s failed: %s", key[2], exc)
    return stats
