from __future__ import annotations


def ecosystem_segment(
    path: str | None,
    *,
    host: str | None = None,
    log_source: str | None = None,
) -> str:
    p = (path or "").lower()
    h = f"{host or ''} {log_source or ''}".lower()

    if "lottery" in h or "ailottery" in h or "/lottery" in p:
        return "lottery"
    if "alien-monitor" in h or p.startswith("/monitor"):
        return "monitor"
    if p.startswith("/pulse"):
        return "pulse"
    if p.startswith("/arena") or p.startswith("/argus") or "docker:argus" in h:
        return "argus"
    if p.startswith("/grafana"):
        return "grafana"
    if p.startswith("/prometheus"):
        return "prometheus"
    if p.startswith("/landing-page-generation"):
        return "landing-gen"
    if p.startswith("/wot") or p.startswith("/aimarket/") or "iot.modelmarket" in h or "gaia.modelmarket" in h:
        return "gaia"
    if "basanos.modelmarket" in h:
        return "basanos"
    if "themis.modelmarket" in h:
        return "themis"
    if "/.well-known/ai-market" in p:
        return "hub-federation"
    if p.startswith("/api/"):
        return "api"
    if any(
        p.startswith(prefix)
        for prefix in (
            "/platon",
            "/family",
            "/chronos",
            "/fermat",
            "/landauer",
            "/percola",
            "/oracle",
            "/metis",
            "/ablation",
            "/dioscuri",
            "/helios",
        )
    ):
        return "oracles"
    if "oracles.modelmarket" in h:
        return "oracles"
    if "modeldev.modelmarket" in h:
        return "modeldev-landing"
    if "magic-ai-factory" in h:
        return "factory"
    if "metis.modelmarket" in h:
        return "metis"
    if "modelmarket.dev" in h and "modeldev" not in h:
        return "hub"
    if p in ("/", ""):
        return "root"
    return "other"
