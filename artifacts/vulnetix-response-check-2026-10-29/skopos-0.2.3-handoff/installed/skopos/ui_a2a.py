"""SKOPOS dashboard section — the A2A wire: watching the agents talk to each other.

MCP traffic is agent→tool and looks like ordinary HTTP. A2A is different: it carries *delegations*
between peers, which is what an operator actually wants to watch — who asked whom to do what, was
it accepted or rejected, and how long it took. MOMUS delegates ``remediate`` to SKOPOS; SKOPOS calls
MOMUS's ``retest`` skill as the deploy gate.

Like the board next to it, this renders envelopes the conductor **pushed into the SKOPOS store**.
The observer's own SQLite (``a2a_events.db``) lives on the conductor host and is not reachable from
here, and instantiating an ``A2AObserver`` on the dashboard host would only create an empty database
in the dashboard's working directory. Summaries stay bounded and inert: A2A text is partly
attacker-influenced, so nothing is rendered as markdown.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

import pandas as pd
import streamlit as st

from skopos.i18n import t_or
from skopos.ui import display_dataframe
from skopos.ui_remediation import scrub_text

_DIR_ICON = {"in": "⬇", "out": "⬆"}
_DIR_LABEL_EN = {"in": "in", "out": "out"}
_STATE_ICON = {
    "completed": "✅",
    "working": "⏳",
    "submitted": "📨",
    "rejected": "⛔",
    "failed": "⚠️",
}
_DASH = "—"


def _artifacts(value: Any) -> str:
    """Artifact *kinds* only — the observer never stores their contents."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return scrub_text(value, 80)
    if isinstance(value, list):
        return ", ".join(scrub_text(item, 32) for item in value[:8])
    return ""


def a2a_rows(raw_rows: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Flatten pushed A2A envelopes. Total: a malformed record is skipped, never raised."""
    rows: list[dict[str, Any]] = []
    for raw in list(raw_rows or []):
        if not isinstance(raw, Mapping):
            continue
        try:
            latency = raw.get("latency_ms")
            rows.append({
                "ts": scrub_text(raw.get("ts_utc") or raw.get("ts"), 32),
                "direction": str(raw.get("direction") or "").strip().lower(),
                "peer": scrub_text(raw.get("peer"), 48),
                "skill": scrub_text(raw.get("skill"), 48),
                "state": str(raw.get("state") or "").strip().lower(),
                "ok": bool(raw.get("ok")) if raw.get("ok") is not None else None,
                "latency_ms": int(latency) if isinstance(latency, (int, float)) else None,
                "finding_id": scrub_text(raw.get("finding_id"), 16),
                "summary": scrub_text(raw.get("summary")),
                "artifacts": _artifacts(raw.get("artifacts_json") or raw.get("artifacts")),
            })
        except Exception:  # noqa: BLE001 - one bad envelope must not blank the strip
            continue
    rows.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
    return rows


def event_rows(observer: Any, limit: int = 100) -> list[dict[str, Any]]:
    """Compat shim for the conductor-side caller that owns an A2AObserver.

    The dashboard keeps ``direction`` raw and applies the arrow at render time, because the label
    next to it is translated. Nothing but the observer's own test reads this decorated form; it can
    go once that test flattens ``observer.recent()`` through ``a2a_rows`` itself. Duck-typed on
    purpose — importing A2AObserver here would pull the conductor package into the dashboard.
    """
    rows = a2a_rows(observer.recent(limit))
    for r in rows:
        r["direction"] = f"{_DIR_ICON.get(r['direction'], '•')} {r['direction']}".strip()
    return rows


def a2a_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Counted from the pushed rows themselves — the conductor's own stats() is not reachable."""
    items = list(rows)
    latencies = [r["latency_ms"] for r in items if isinstance(r.get("latency_ms"), int)]
    by_skill: dict[str, int] = {}
    by_peer: dict[str, int] = {}
    for r in items:
        if r.get("skill"):
            by_skill[str(r["skill"])] = by_skill.get(str(r["skill"]), 0) + 1
        if r.get("peer"):
            by_peer[str(r["peer"])] = by_peer.get(str(r["peer"]), 0) + 1
    return {
        "total": len(items),
        "rejected": sum(1 for r in items if r.get("ok") is False or r.get("state") == "rejected"),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "by_skill": by_skill,
        "by_peer": by_peer,
    }


def _direction_cell(direction: str, locale: str) -> str:
    icon = _DIR_ICON.get(direction, "•")
    label = t_or(f"remediation.a2a_dir_{direction}", locale, _DIR_LABEL_EN.get(direction, direction))
    return f"{icon} {label}".strip()


def _state_cell(state: str, locale: str) -> str:
    if not state:
        return _DASH
    icon = _STATE_ICON.get(state, "•")
    return f"{icon} {t_or(f'remediation.a2a_state_{state}', locale, state)}"


def render_a2a_strip(
    rows: Iterable[Mapping[str, Any]],
    *,
    locale: str = "en",
    key_prefix: str = "remediation_a2a",
) -> None:
    """Envelope counters plus the wire itself: skill, direction, peer, latency."""
    items = list(rows)
    if not items:
        return
    s = a2a_summary(items)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t_or("remediation.a2a_kpi_total", locale, "Envelopes"), s["total"])
    c2.metric(t_or("remediation.a2a_kpi_rejected", locale, "Rejected"), s["rejected"])
    c3.metric(
        t_or("remediation.a2a_kpi_latency", locale, "Avg latency"),
        f"{s['avg_latency_ms']:.0f} ms" if s["avg_latency_ms"] is not None else _DASH,
    )
    c4.metric(t_or("remediation.a2a_kpi_peers", locale, "Peers"), len(s["by_peer"]))

    header = {
        "ts": t_or("remediation.col_ts", locale, "When"),
        "skill": t_or("remediation.a2a_col_skill", locale, "Skill"),
        "direction": t_or("remediation.a2a_col_direction", locale, "Direction"),
        "peer": t_or("remediation.a2a_col_peer", locale, "Peer"),
        "state": t_or("remediation.col_state", locale, "State"),
        "latency": t_or("remediation.a2a_col_latency", locale, "Latency (ms)"),
        "finding": t_or("remediation.a2a_col_finding", locale, "Finding"),
        "summary": t_or("remediation.a2a_col_summary", locale, "Summary"),
        "artifacts": t_or("remediation.a2a_col_artifacts", locale, "Artifacts"),
    }
    display_dataframe(
        pd.DataFrame([{
            header["ts"]: r.get("ts") or _DASH,
            header["skill"]: r.get("skill") or _DASH,
            header["direction"]: _direction_cell(str(r.get("direction") or ""), locale),
            header["peer"]: r.get("peer") or _DASH,
            header["state"]: _state_cell(str(r.get("state") or ""), locale),
            header["latency"]: r.get("latency_ms"),
            header["finding"]: r.get("finding_id") or _DASH,
            header["summary"]: r.get("summary") or _DASH,
            header["artifacts"]: r.get("artifacts") or _DASH,
        } for r in items]),
        key=f"{key_prefix}_wire",
        use_container_width=True,
        hide_index=True,
    )


def render_a2a_empty(reason: str, *, locale: str = "en") -> None:
    """One sentence, and only what the store can prove — see render_remediation_empty."""
    if reason == "no_contract":
        st.info(t_or(
            "remediation.a2a_empty_no_contract", locale,
            "No A2A envelopes: the conductor's wire log is not part of the push contract yet, so it "
            "stays on the conductor's own host and none of it has reached this dashboard.",
        ))
        return
    if reason == "no_channel":
        st.info(t_or(
            "remediation.a2a_empty_no_channel", locale,
            "No A2A envelopes: no push credential is enrolled on this dashboard, so the conductor "
            "has no channel to deliver its wire log over.",
        ))
        return
    st.info(t_or(
        "remediation.a2a_empty", locale,
        "No A2A envelopes have been pushed to this dashboard yet.",
    ))
