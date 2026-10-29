"""SKOPOS dashboard section — the remediation board: what MOMUS made us fix.

One row per MOMUS finding, as it moved through fix → MOMUS re-test → signed deploy order →
in-place verification: the gate verdict, the order id, and what the node agent actually did or why
it refused.

Two constraints shape this module, and both changed it from its first draft:

* It renders rows the conductor **pushed into the SKOPOS store**, never a live ``Conductor``. The
  conductor runs on another host, is loopback-only, and holds the MOMUS operator token plus its
  signing key — building a ``RemediationConfig`` here would move the control plane into the
  dashboard process, and would read an empty local ``jobs.jsonl`` anyway (no shared volume).
* Everything here is untrusted text. MOMUS's verdict ``detail`` and the Factory's error string ride
  into history notes verbatim, so free text is scrubbed, length-bounded, and rendered inert
  (dataframe cells and ``st.code``) rather than as markdown.

The board is read-only by construction: it has no path back to the conductor, and the pushed copy
is never treated as authoritative.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping

import pandas as pd
import streamlit as st

from skopos.i18n import t_or
from skopos.ui import display_dataframe

#: The JobState vocabulary (skopos/remediation/jobs.py). Literals on purpose: these arrive as
#: pushed *text*, and importing skopos.remediation would drag the conductor package — its HTTP
#: clients and its config — into the dashboard process. An unknown state still renders.
_STATE_ICON = {
    "received": "🟦",
    "fixing": "🛠️",
    "retesting": "🔍",
    "deploying": "🚀",
    "verifying": "🧪",
    "done": "✅",
    "failed": "🔁",
    "escalated": "🧑‍⚖️",
}
_STATE_LABEL_EN = {
    "received": "received",
    "fixing": "fixing (Factory)",
    "retesting": "re-testing (MOMUS gate)",
    "deploying": "deploying (node agent)",
    "verifying": "verifying in place",
    "done": "done",
    "failed": "failed — retrying",
    "escalated": "escalated to human",
}
_SEVERITY_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
_QUEUE_LABEL_EN = {"pending": "published, not claimed", "claimed": "claimed by the agent",
                   "reported": "agent reported back"}

#: Stands in for a value that is shaped like an address rather than a label. Same token the
#: store writes (node_remediation._label) and the same spirit as redact.REDACTED — one
#: vocabulary end to end, and a symbol, so it needs no translation.
REDACTED_LABEL = "<redacted>"

# Same rules as A2AObserver.scrub (a2a_observer.py:57-66), duplicated rather than imported for the
# reason in the docstring: a finding title can quote a hostile advisory verbatim.
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_SECRETISH = re.compile(r"(?i)(authorization|api[_-]?key|token|secret|password)\s*[:=]\s*\S+")
#: component/service/host are internal labels and DeployOrder.host is literally the component, so
#: a SKOPOS_AGENT_HOSTS url or a bare address can land in one. This repo has leaked private hosts
#: through committed text before; an address is not something a dashboard should publish.
_ADDRESSISH = re.compile(r"(://|@|\d{1,3}(?:\.\d{1,3}){3}|\[[0-9a-fA-F:]+\])")

_DASH = "—"


# ── value handling ───────────────────────────────────────────────────────────
def scrub_text(value: Any, limit: int = 240) -> str:
    """Bounded, control-character-free, secret-shaped-text-free rendering of untrusted text."""
    if value is None:
        return ""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    s = _SECRETISH.sub(r"\1=<redacted>", s)
    s = _CTRL.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _label(value: Any, limit: int = 64) -> str:
    """A short internal label (component, service, agent id), redacted if it looks like a host."""
    s = scrub_text(value, limit)
    if not s:
        return ""
    return REDACTED_LABEL if _ADDRESSISH.search(s) else s


def _image_label(value: Any, limit: int = 64) -> str:
    """An image ref with its registry host dropped — that host is often private infrastructure."""
    s = scrub_text(value, 200)
    if not s:
        return ""
    parts = s.split("/")
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0]):
        parts = parts[1:]
    out = "/".join(parts)[:limit]
    return REDACTED_LABEL if _ADDRESSISH.search(out) else out


def _key_material(value: Any, limit: int = 20) -> str:
    """Verifying keys and signatures are public by construction — shown, but truncated."""
    s = scrub_text(value, 200)
    return (s[:limit] + "…") if len(s) > limit else s


def _pick(row: Mapping[str, Any], *names: str) -> Any:
    """First present, non-null value. The push side may send flat columns or a JSON blob."""
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (str, bytes)):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, (str, bytes)):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _tri(*values: Any) -> bool | None:
    """Tri-state read: True / False / unknown. "not True" must never be rendered as "fixed"."""
    for v in values:
        if v is None:
            continue
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "t"):
            return True
        if s in ("0", "false", "no", "f"):
            return False
    return None


def _int(value: Any) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def state_label(state: str, locale: str = "en") -> str:
    """Icon + translated state name; an unknown state falls back to its own text."""
    key = str(state or "").strip().lower()
    icon = _STATE_ICON.get(key, "•")
    label = t_or(f"remediation.state_{key}", locale, _STATE_LABEL_EN.get(key, key or _DASH))
    return f"{icon} {label}".strip()


def _severity_label(severity: str) -> str:
    key = str(severity or "").strip().lower()
    icon = _SEVERITY_ICON.get(key, "⚪")
    return f"{icon} {key.upper()}" if key else _DASH


def _timeline(history: list[Any], state: str, locale: str) -> str:
    """The path the job actually took: one icon per transition, then where it stands now."""
    seq: list[str] = []
    for entry in history:
        if not isinstance(entry, Mapping):
            continue
        s = str(entry.get("state") or "").strip().lower()
        if s and (not seq or seq[-1] != s):
            seq.append(s)
    if not seq and state:
        seq = [state]
    chain = " → ".join(_STATE_ICON.get(s, "•") for s in seq[-8:])
    return f"{chain}  {state_label(state, locale)}".strip() if chain else state_label(state, locale)


# ── flattening ───────────────────────────────────────────────────────────────
def job_rows(raw_rows: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Flatten pushed job records into display-ready rows.

    Total by construction: a missing, renamed or malformed field becomes an empty value rather than
    an exception, and a record that is not a mapping is skipped (the caller compares lengths and
    says so). Nothing here invents a value — an unknown verdict stays unknown.
    """
    rows: list[dict[str, Any]] = []
    for raw in list(raw_rows or []):
        if not isinstance(raw, Mapping):
            continue
        try:
            rows.append(_job_row(raw))
        except Exception:  # noqa: BLE001 - one bad record must not blank the board
            continue
    rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
    return rows


def _job_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    """One store row → one display row.

    The store keeps the queryable fields as columns and the rest inside ``summary`` (parsed from
    ``summary_json``) — see skopos/node_remediation.py. Columns win, the summary fills the gaps, and
    both are optional so a row written by an older or newer push still renders.
    """
    summary = _as_dict(_pick(raw, "summary", "summary_json"))
    gate = _as_dict(summary.get("gate_verdict") or _pick(raw, "gate_verdict"))
    post = _as_dict(summary.get("post_deploy_verdict") or _pick(raw, "post_deploy_verdict"))
    deploy = _as_dict(summary.get("deploy") or _pick(raw, "deploy", "deploy_order"))
    queue = _as_dict(summary.get("queue") or _pick(raw, "queue"))
    agent = _as_dict(summary.get("agent_result") or _pick(raw, "agent_result"))
    history = _as_list(summary.get("history") or _pick(raw, "history"))
    state = str(_pick(raw, "state") or summary.get("state") or "").strip().lower()
    return {
        "finding_id": scrub_text(_pick(raw, "finding_id") or summary.get("finding_id"), 128),
        "component": _label(_pick(raw, "component") or summary.get("component")),
        "probe": scrub_text(_pick(raw, "probe") or summary.get("probe"), 80),
        "severity": str(_pick(raw, "severity") or summary.get("severity") or "").strip().lower(),
        "route": scrub_text(_pick(raw, "route") or summary.get("route"), 32),
        "state": state,
        "attempts": _int(_pick(raw, "attempts") or summary.get("attempts")),
        "history": [h for h in history if isinstance(h, Mapping)],
        "history_truncated": bool(summary.get("history_truncated") or summary.get("truncated")),
        "gate_fixed": _tri(_pick(raw, "gate_fixed"), gate.get("fixed")),
        "gate_outcome": scrub_text(_pick(raw, "gate_outcome") or gate.get("outcome"), 32),
        "gate_detail": scrub_text(gate.get("detail")),
        "gate_checked_at": scrub_text(gate.get("checked_at"), 32),
        "verifier_pubkey": _key_material(gate.get("verifier_pubkey")),
        "gate_signature": _key_material(_signature(gate.get("signature"))),
        "post_fixed": _tri(post.get("fixed")),
        "post_outcome": scrub_text(post.get("outcome"), 32),
        "deploy_order_id": scrub_text(_pick(raw, "deploy_order_id") or deploy.get("order_id"), 128),
        "deploy_service": _label(deploy.get("service")),
        "deploy_image": _image_label(deploy.get("image")),
        "order_created_at": scrub_text(deploy.get("created_at"), 32),
        "conductor_pubkey": _key_material(deploy.get("conductor_pubkey")),
        "order_signature": _key_material(_signature(deploy.get("signature"))),
        "queue_state": scrub_text(queue.get("state") or _pick(raw, "queue_state"), 32).lower(),
        "claimed_by": _label(queue.get("claimed_by")),
        "claimed_at": scrub_text(queue.get("claimed_at"), 32),
        "agent_deployed": _tri(_pick(raw, "deployed"), agent.get("deployed")),
        "agent_refused": _tri(agent.get("refused")),
        "agent_reason": scrub_text(agent.get("reason")),
        "agent_executed_at": scrub_text(agent.get("executed_at"), 32),
        "server_name": _label(_pick(raw, "server_name")),
        # The stored blob itself, so the detail view can show exactly what was pushed rather than a
        # re-rendering of it. Already bounded and scrubbed by the store; bounded again for display.
        "summary_raw": scrub_text(_pick(raw, "summary_json")
                                  or (json.dumps(summary, ensure_ascii=False, sort_keys=True)
                                      if summary else ""), 8000),
        "created_at": scrub_text(_pick(raw, "created_at_utc") or summary.get("created_at"), 32),
        "updated_at": scrub_text(_pick(raw, "updated_at_utc") or summary.get("updated_at"), 32),
        "received_at": scrub_text(_pick(raw, "received_at_utc"), 32),
    }


def _signature(value: Any) -> str:
    """The store flattens a signature to its value; a raw envelope still carries the dict."""
    if isinstance(value, Mapping):
        return str(value.get("value") or "")
    return str(value or "")


def board_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """The four numbers the headline strip answers with. Counted, never estimated."""
    items = list(rows)
    return {
        "closed": sum(1 for r in items if r.get("state") == "done"),
        "confirmed_fixed": sum(1 for r in items if r.get("gate_fixed") is True),
        "escalated": sum(1 for r in items if r.get("state") == "escalated"),
        "orders_signed": sum(1 for r in items if r.get("deploy_order_id")),
        "total": len(items),
    }


# ── rendering ────────────────────────────────────────────────────────────────
def render_remediation_headline(rows: Iterable[Mapping[str, Any]], *, locale: str = "en") -> None:
    """Four counters: closed, MOMUS-confirmed fixed, escalated, deploy orders signed."""
    s = board_summary(rows)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        t_or("remediation.kpi_closed", locale, "Jobs closed"), s["closed"],
        help=t_or("remediation.kpi_closed_hint", locale,
                  "Findings whose job reached done: fixed, deployed and verified in place."),
    )
    c2.metric(
        t_or("remediation.kpi_fixed", locale, "Findings fixed"), s["confirmed_fixed"],
        help=t_or("remediation.kpi_fixed_hint", locale,
                  "MOMUS re-tested the patched build and signed a fixed verdict. Anything short of "
                  "that is not counted here."),
    )
    c3.metric(
        t_or("remediation.kpi_escalated", locale, "Escalated now"), s["escalated"],
        help=t_or("remediation.kpi_escalated_hint", locale,
                  "Waiting on a human: a security-core finding, an unverifiable ticket, a gate that "
                  "could not run, or an exhausted attempt budget."),
    )
    c4.metric(
        t_or("remediation.kpi_orders", locale, "Deploy orders signed"), s["orders_signed"],
        help=t_or("remediation.kpi_orders_hint", locale,
                  "Conductor-signed deploy orders published for a node agent to claim."),
    )


def _gate_cell(row: Mapping[str, Any], locale: str) -> str:
    fixed = row.get("gate_fixed")
    outcome = row.get("gate_outcome")
    if fixed is True:
        text = t_or("remediation.gate_fixed", locale, "✅ fixed")
    elif fixed is False:
        text = t_or("remediation.gate_not_fixed", locale, "⛔ not fixed")
    else:
        return t_or("remediation.gate_unknown", locale, "— gate has not returned")
    return f"{text} ({outcome})" if outcome else text


def _agent_cell(row: Mapping[str, Any], locale: str) -> str:
    if row.get("agent_deployed") is True:
        return t_or("remediation.agent_deployed", locale, "🚀 redeployed")
    if row.get("agent_refused") is True:
        reason = row.get("agent_reason") or _DASH
        return t_or("remediation.agent_refused", locale, "⛔ refused: {reason}", reason=reason)
    queue = str(row.get("queue_state") or "")
    if queue:
        return t_or(f"remediation.queue_{queue}", locale, _QUEUE_LABEL_EN.get(queue, queue))
    return t_or("remediation.agent_silent", locale, "— no agent report")


def _board_table(rows: Iterable[Mapping[str, Any]], locale: str) -> pd.DataFrame:
    header = {
        "severity": t_or("remediation.col_severity", locale, "Severity"),
        "component": t_or("remediation.col_component", locale, "Component"),
        "probe": t_or("remediation.col_probe", locale, "Probe"),
        "timeline": t_or("remediation.col_timeline", locale, "Timeline"),
        "gate": t_or("remediation.col_gate", locale, "MOMUS gate"),
        "order": t_or("remediation.col_order", locale, "Deploy order"),
        "agent": t_or("remediation.col_agent", locale, "Node agent"),
        "updated": t_or("remediation.col_updated", locale, "Updated"),
    }
    table = []
    for r in rows:
        table.append({
            header["severity"]: _severity_label(r.get("severity", "")),
            header["component"]: r.get("component") or _DASH,
            header["probe"]: r.get("probe") or _DASH,
            header["timeline"]: _timeline(list(r.get("history") or []), str(r.get("state") or ""), locale),
            header["gate"]: _gate_cell(r, locale),
            header["order"]: r.get("deploy_order_id") or _DASH,
            header["agent"]: _agent_cell(r, locale),
            header["updated"]: r.get("updated_at") or _DASH,
        })
    return pd.DataFrame(table)


def _kv_block(pairs: list[tuple[str, Any]]) -> str:
    """Field/value lines for st.code — monospace and inert, so untrusted text renders as text."""
    width = max((len(k) for k, _v in pairs), default=0)
    lines = []
    for key, value in pairs:
        shown = _DASH if value in (None, "") else value
        lines.append(f"{key.ljust(width)}  {shown}")
    return "\n".join(lines)


def _tri_text(value: bool | None, locale: str) -> str:
    if value is True:
        return t_or("remediation.yes", locale, "yes")
    if value is False:
        return t_or("remediation.no", locale, "no")
    return t_or("remediation.unknown", locale, "unknown")


def _render_job_detail(row: Mapping[str, Any], locale: str, key_prefix: str) -> None:
    st.caption(t_or("remediation.detail_gate", locale, "MOMUS deploy gate (signed verdict)"))
    st.code(_kv_block([
        (t_or("remediation.f_fixed", locale, "fixed"), _tri_text(row.get("gate_fixed"), locale)),
        (t_or("remediation.f_outcome", locale, "outcome"), row.get("gate_outcome")),
        (t_or("remediation.f_detail", locale, "detail"), row.get("gate_detail")),
        (t_or("remediation.f_checked_at", locale, "checked at"), row.get("gate_checked_at")),
        (t_or("remediation.f_verifier", locale, "verifier key"), row.get("verifier_pubkey")),
        (t_or("remediation.f_signature", locale, "signature"), row.get("gate_signature")),
        (t_or("remediation.f_post_fixed", locale, "in-place re-test"),
         f"{_tri_text(row.get('post_fixed'), locale)} ({row.get('post_outcome') or _DASH})"),
    ]), language="text")

    st.caption(t_or("remediation.detail_order", locale, "Signed deploy order"))
    st.code(_kv_block([
        (t_or("remediation.f_order_id", locale, "order id"), row.get("deploy_order_id")),
        (t_or("remediation.f_service", locale, "service"), row.get("deploy_service")),
        (t_or("remediation.f_image", locale, "image"), row.get("deploy_image")),
        (t_or("remediation.f_created_at", locale, "signed at"), row.get("order_created_at")),
        (t_or("remediation.f_conductor", locale, "conductor key"), row.get("conductor_pubkey")),
        (t_or("remediation.f_signature", locale, "signature"), row.get("order_signature")),
        (t_or("remediation.f_queue", locale, "queue state"), row.get("queue_state")),
        (t_or("remediation.f_claimed_by", locale, "claimed by"), row.get("claimed_by")),
        (t_or("remediation.f_claimed_at", locale, "claimed at"), row.get("claimed_at")),
    ]), language="text")

    st.caption(t_or("remediation.detail_agent", locale, "What the node agent did"))
    st.code(_kv_block([
        (t_or("remediation.f_deployed", locale, "deployed"), _tri_text(row.get("agent_deployed"), locale)),
        (t_or("remediation.f_refused", locale, "refused"), _tri_text(row.get("agent_refused"), locale)),
        (t_or("remediation.f_reason", locale, "reason"), row.get("agent_reason")),
        (t_or("remediation.f_executed_at", locale, "executed at"), row.get("agent_executed_at")),
    ]), language="text")

    history = list(row.get("history") or [])
    st.caption(t_or("remediation.detail_history", locale,
                    "Full history — the notes are the conductor's own words, bounded and scrubbed"))
    if history:
        display_dataframe(
            pd.DataFrame([{
                t_or("remediation.col_ts", locale, "When"): scrub_text(h.get("ts"), 32),
                t_or("remediation.col_state", locale, "State"): state_label(str(h.get("state") or ""), locale),
                t_or("remediation.col_note", locale, "Note"): scrub_text(h.get("note")),
            } for h in history]),
            key=f"{key_prefix}_hist_{row.get('finding_id') or len(history)}",
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption(t_or("remediation.no_history", locale, "No transitions were pushed with this job."))
    if row.get("history_truncated"):
        st.caption(t_or("remediation.history_truncated", locale,
                        "The timeline was trimmed to fit the push size budget — the conductor holds "
                        "the full one."))

    if row.get("summary_raw"):
        st.caption(t_or("remediation.detail_summary", locale, "Raw pushed summary"))
        st.code(str(row.get("summary_raw")), language="json")


def render_remediation_board(
    rows: Iterable[Mapping[str, Any]],
    *,
    locale: str = "en",
    key_prefix: str = "remediation",
) -> None:
    """The board: one line per finding, plus an expander per finding for the full history."""
    items = list(rows)
    if not items:
        return
    display_dataframe(
        _board_table(items, locale),
        key=f"{key_prefix}_board",
        use_container_width=True,
        hide_index=True,
    )
    for idx, row in enumerate(items):
        head = " · ".join(part for part in (
            state_label(str(row.get("state") or ""), locale),
            _severity_label(str(row.get("severity") or "")),
            row.get("component") or _DASH,
            row.get("probe") or _DASH,
        ) if part)
        with st.expander(head):
            st.caption(_kv_head(row, locale))
            _render_job_detail(row, locale, f"{key_prefix}_{idx}")


def _kv_head(row: Mapping[str, Any], locale: str) -> str:
    attempts = row.get("attempts")
    return " · ".join([
        f"{t_or('remediation.f_finding', locale, 'finding')}: {row.get('finding_id') or _DASH}",
        f"{t_or('remediation.f_route', locale, 'route')}: {row.get('route') or _DASH}",
        f"{t_or('remediation.f_attempts', locale, 'attempts')}: {attempts if attempts is not None else _DASH}",
        f"{t_or('remediation.f_updated', locale, 'updated')}: {row.get('updated_at') or _DASH}",
    ])


def render_remediation_empty(reason: str, *, locale: str = "en") -> None:
    """One sentence saying exactly why the board is empty. Never a placeholder row.

    ``reason`` comes from the store, not from a guess: ``no_channel`` means no push credential is
    enrolled here at all, so the conductor has no channel to deliver over; ``nothing_pushed`` means
    the channel exists and has carried nothing yet.
    """
    if reason == "no_channel":
        st.info(t_or(
            "remediation.empty_no_channel", locale,
            "Nothing to show: no push credential is enrolled on this dashboard, so the conductor "
            "has no channel to deliver remediation over.",
        ))
        return
    st.info(t_or(
        "remediation.empty_nothing_pushed", locale,
        "Nothing to show: the conductor has not pushed a remediation job to this dashboard yet.",
    ))
