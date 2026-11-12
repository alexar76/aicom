"""The onboarding funnel of the federation: knock → assay → admitted → first routed call → first paid call.

Owner, 2026-11-08: show on /hubs where each hub that came to this one stands, so an operator — and the hub
holder — can see which step stopped them. Every step is read from what this hub already records: the knock
(``peers.first_seen``), the admission assay (``peer_assays``), admission (the peer is in ``peers``, not
pending), and the first delivered and first paid call routed to it (``invocation_stats``). Nothing here is a
claim of the peer's.

The totals count hubs that are not the operator's own: not pinned by the operator (``canonical_id``) and not on
this hub's own site (``*.modelmarket.dev`` for modelmarket.dev). The funnel is about newcomers, and the operator's
own nodes would only inflate it. Every hub is still listed, the operator's marked as such.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from aimarket_hub.peer_liveness import liveness

STAGES = ("knocked", "assayed", "admitted", "routed", "paid")


def operators_own(config: Any) -> Callable[[Any], bool]:
    """Is a peer the operator's own: pinned by them, or on this hub's own site?"""
    from aimarket_hub.federation_assay import site_of
    from aimarket_hub.peer_identity import canonical_id_for

    own_site = site_of(str(getattr(config, "hub_url", "") or ""))

    def check(peer: Any) -> bool:
        if canonical_id_for(peer, config):
            return True
        return bool(own_site) and site_of(str(getattr(peer, "url", "") or "")) == own_site

    return check


def _next_step(row: dict[str, Any]) -> str:
    if not row["admitted"]:
        verdict = row["assay_verdict"]
        if verdict == "pass":
            return "assay passed; waiting for admission"
        if verdict in ("fail", "review"):
            return "the admission assay did not pass: see the dossier"
        return "waiting for the admission assay"
    if row["liveness"] == "silent":
        return f"not answering crawls for {row['silent_days']} days"
    if not row["first_routed_at"]:
        return "admitted; no buyer has been routed here yet"
    if not row["first_paid_at"]:
        return "serves routed calls; no paid call yet"
    return "selling"


def build(*, peers: Iterable[Any], pending: Iterable[Any], assay: Callable[[str], dict | None],
          stats: dict[str, dict], pinned: Callable[[Any], bool], now: float | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for admitted, group in ((True, peers), (False, pending)):
        for p in group:
            url = str(getattr(p, "url", "") or "")
            dossier = assay(url) or {}
            st = stats.get(url, {})
            row = {
                "url": url,
                "name": str(getattr(p, "name", "") or url),
                "pinned_by_operator": bool(pinned(p)),
                "knocked_at": str(getattr(p, "first_seen", "") or ""),
                "assay_verdict": dossier.get("verdict") or None,
                "assay_ran_at": dossier.get("ran_at") or "",
                "admitted": admitted,
                "first_routed_at": st.get("first_routed_at", ""),
                "routed_calls": int(st.get("routed_calls", 0)),
                "first_paid_at": st.get("first_paid_at", ""),
                "paid_calls": int(st.get("paid_calls", 0)),
                **(liveness(getattr(p, "last_crawl", ""), now=now) if admitted
                   else {"liveness": "pending", "silent_days": None}),
            }
            reached = [
                bool(row["knocked_at"]) or admitted,
                bool(row["assay_verdict"]) or admitted,
                admitted,
                bool(row["first_routed_at"]),
                bool(row["first_paid_at"]),
            ]
            row["stage"] = next((STAGES[i] for i in range(len(STAGES) - 1, -1, -1) if reached[i]), "knocked")
            row["next_step"] = _next_step(row)
            rows.append(row)
    order = {s: i for i, s in enumerate(STAGES)}
    rows.sort(key=lambda r: (r["pinned_by_operator"], -order[r["stage"]], r["url"]))
    newcomers = [r for r in rows if not r["pinned_by_operator"]]
    totals = {
        "knocked": len(newcomers),
        "assay_passed": sum(1 for r in newcomers if r["assay_verdict"] == "pass" or r["admitted"]),
        "admitted": sum(1 for r in newcomers if r["admitted"]),
        "routed": sum(1 for r in newcomers if r["first_routed_at"]),
        "paid": sum(1 for r in newcomers if r["first_paid_at"]),
        "silent": sum(1 for r in newcomers if r["liveness"] == "silent"),
    }
    return {"stages": list(STAGES), "totals": totals,
            "counts": "hubs that are not this operator's (not pinned, not on this hub's own site)", "hubs": rows}
