"""
Discovery pipeline: opportunity signals -> validated ranked ideas.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from llm import GenerationConfig, LLMRouter
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY
from marketplace_taxonomy import MARKETPLACE_CATEGORY_IDS, slug_to_marketplace_category

from core.paths import discovery_dir

logger = logging.getLogger(__name__)

DISCOVERY_DIR = discovery_dir()


class SourceRuntime:
    def __init__(self, name: str, min_interval_sec: float = 1.0, max_backoff_sec: float = 180.0):
        self.name = name
        self.min_interval_sec = float(min_interval_sec)
        self.max_backoff_sec = float(max_backoff_sec)
        self.last_call_ts = 0.0
        self.backoff_until_ts = 0.0
        self.fail_streak = 0
        self.success_count = 0
        self.failure_count = 0
        self.last_error = ""
        self.last_latency_ms = 0

    def can_call(self, now: float) -> tuple[bool, str]:
        if now < self.backoff_until_ts:
            return False, f"backoff_active:{round(self.backoff_until_ts - now, 2)}s"
        if now - self.last_call_ts < self.min_interval_sec:
            return False, f"rate_limited:{round(self.min_interval_sec - (now - self.last_call_ts), 2)}s"
        return True, "ok"

    def mark_call(self, now: float, latency_ms: int) -> None:
        self.last_call_ts = now
        self.last_latency_ms = int(latency_ms)

    def mark_success(self) -> None:
        self.success_count += 1
        self.fail_streak = 0
        self.last_error = ""
        self.backoff_until_ts = 0.0

    def mark_failure(self, now: float, error: str) -> None:
        self.failure_count += 1
        self.fail_streak += 1
        self.last_error = (error or "")[:280]
        # Exponential backoff with cap.
        wait_sec = min(self.max_backoff_sec, float(2 ** min(self.fail_streak, 8)))
        self.backoff_until_ts = now + wait_sec

    def to_health(self) -> dict[str, Any]:
        status = "healthy"
        if self.fail_streak >= 3:
            status = "degraded"
        if self.fail_streak >= 6:
            status = "unhealthy"
        return {
            "source": self.name,
            "status": status,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "fail_streak": self.fail_streak,
            "last_error": self.last_error,
            "last_latency_ms": self.last_latency_ms,
            "last_call_ts": self.last_call_ts,
            "backoff_until_ts": self.backoff_until_ts,
        }


def _duckduckgo_search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    try:
        from duckduckgo_search import DDGS

        out: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for row in ddgs.text(query, max_results=max_results):
                out.append(
                    {
                        "title": str(row.get("title") or "").strip(),
                        "snippet": str(row.get("body") or "").strip(),
                        "url": str(row.get("href") or "").strip(),
                    }
                )
        return out
    except Exception as exc:
        logger.warning("Discovery search failed for query='%s': %s", query, exc)
        return []


def _reddit_search(query: str, limit: int = 8) -> list[dict[str, str]]:
    """
    Lightweight Reddit search using the public JSON endpoint.
    No OAuth required for basic read access, but User-Agent is mandatory.
    """
    try:
        q = urllib.parse.quote_plus(query)
        url = f"https://www.reddit.com/search.json?q={q}&limit={max(1, min(limit, 25))}&sort=new&t=month"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "aifactory-discovery/1.0 (+https://example.local)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        children = (((payload or {}).get("data") or {}).get("children") or [])
        out: list[dict[str, str]] = []
        for item in children:
            data = (item or {}).get("data") or {}
            title = str(data.get("title") or "").strip()
            snippet = str(data.get("selftext") or data.get("subreddit_name_prefixed") or "").strip()
            permalink = str(data.get("permalink") or "").strip()
            url = f"https://www.reddit.com{permalink}" if permalink else str(data.get("url") or "").strip()
            if title and url:
                out.append({"title": title, "snippet": snippet[:500], "url": url})
        return out
    except Exception as exc:
        logger.warning("Discovery Reddit API search failed for query='%s': %s", query, exc)
        return []


def _hn_search(query: str, limit: int = 10) -> list[dict[str, str]]:
    """
    Hacker News API (Algolia mirror) query.
    """
    try:
        q = urllib.parse.quote_plus(query)
        url = f"https://hn.algolia.com/api/v1/search?query={q}&tags=story&hitsPerPage={max(1, min(limit, 30))}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "aifactory-discovery/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        hits = (payload or {}).get("hits") or []
        out: list[dict[str, str]] = []
        for item in hits:
            title = str(item.get("title") or "").strip()
            story_url = str(item.get("url") or "").strip()
            hn_id = str(item.get("objectID") or "").strip()
            url = story_url or (f"https://news.ycombinator.com/item?id={hn_id}" if hn_id else "")
            snippet = str(item.get("story_text") or item.get("comment_text") or "").strip()
            if title and url:
                out.append({"title": title, "snippet": snippet[:500], "url": url})
        return out
    except Exception as exc:
        logger.warning("Discovery HN API search failed for query='%s': %s", query, exc)
        return []


def _github_repo_search(query: str, limit: int = 10) -> list[dict[str, str]]:
    """
    GitHub REST search API (public, unauthenticated quota).
    """
    try:
        q = urllib.parse.quote_plus(query)
        url = (
            "https://api.github.com/search/repositories"
            f"?q={q}&sort=updated&order=desc&per_page={max(1, min(limit, 30))}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "aifactory-discovery/1.0",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        items = (payload or {}).get("items") or []
        out: list[dict[str, str]] = []
        for item in items:
            full_name = str(item.get("full_name") or "").strip()
            desc = str(item.get("description") or "").strip()
            html_url = str(item.get("html_url") or "").strip()
            stars = item.get("stargazers_count")
            title = full_name
            if full_name and stars is not None:
                title = f"{full_name} (stars:{stars})"
            if title and html_url:
                out.append({"title": title, "snippet": desc[:500], "url": html_url})
        return out
    except Exception as exc:
        logger.warning("Discovery GitHub API search failed for query='%s': %s", query, exc)
        return []


def _clamp(v: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, float(v)))


def _safe_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


def _pick_category(raw: Any, existing_categories: list[str]) -> str:
    mapped = slug_to_marketplace_category(raw)
    if mapped:
        return mapped
    counts = {k: 0 for k in MARKETPLACE_CATEGORY_IDS}
    for item in existing_categories:
        m = slug_to_marketplace_category(item)
        if m in counts:
            counts[m] += 1
    least = min(counts.values()) if counts else 0
    for cat in MARKETPLACE_CATEGORY_IDS:
        if counts.get(cat, 0) == least:
            return cat
    return "saas"


def _heuristic_full_software_potential(idea: str) -> float:
    """Bump ranking when brief implies dashboard/API/auth/data (Director prefers full_software-shaped ideas)."""
    blob = (idea or "").lower()
    keys = (
        "dashboard",
        "auth",
        "login",
        "api",
        "postgres",
        "database",
        "saas",
        "team",
        "crud",
        "jwt",
        "backend",
        "sync",
        "tenant",
        "role",
    )
    hits = sum(1 for k in keys if k in blob)
    return _clamp(4.0 + min(6.0, hits * 0.65))


def compute_idea_score(
    metrics: dict[str, float],
    *,
    data_root=None,
    category: str = "",
    delivery_profile: str = "",
) -> dict[str, float]:
    # Weighted objective score for early-stage filtering.
    weights = {
        "tam": 0.18,
        "pain_severity": 0.18,
        "differentiation": 0.18,
        "feasibility": 0.14,
        "strategic_fit": 0.09,
        "evidence_strength": 0.09,
        "implementation_effort_inverse": 0.05,
        "full_software_potential": 0.09,
    }
    # Outcome prior (L2 demand loop) only applies when an outcomes ledger is reachable
    # (data_root given). Without it the score stays exactly as before — no outcome term.
    outcome_fit_value: float | None = None
    if data_root is not None:
        try:
            from pathlib import Path

            from core.outcome_memory import outcome_fit_score, outcome_prior_weight

            outcome_w = outcome_prior_weight()
            if outcome_w > 0:
                scale = 1.0 - outcome_w
                weights = {k: v * scale for k, v in weights.items()}
                weights["outcome_fit"] = outcome_w
                outcome_fit_value = _clamp(
                    outcome_fit_score(
                        Path(data_root),
                        category=category,
                        delivery_profile=delivery_profile,
                    )
                )
        except Exception:
            weights.pop("outcome_fit", None)
            outcome_fit_value = None
    normalized = {k: _clamp(metrics.get(k, 0.0)) for k in weights if k != "outcome_fit"}
    if outcome_fit_value is not None:
        normalized["outcome_fit"] = outcome_fit_value
    total = sum(normalized[k] * w for k, w in weights.items())
    return {
        "total": round(total, 3),
        "confidence": round(
            _clamp(
                (
                    normalized["evidence_strength"] * 0.5
                    + normalized["pain_severity"] * 0.25
                    + normalized["differentiation"] * 0.25
                ),
                0.0,
                10.0,
            ),
            3,
        ),
    }


class DiscoveryPipeline:
    def __init__(self, router: LLMRouter, data_dir: Path = DISCOVERY_DIR):
        self.router = router
        self.data_dir = data_dir
        self.signals_db = self.data_dir / "signals.jsonl"
        self.ranked_ideas_file = self.data_dir / "ranked_ideas.json"
        self.weekly_digest_file = self.data_dir / "weekly_digest.md"
        self.source_health_file = self.data_dir / "source_health.json"
        self.signal_ttl_days = int(os.environ.get("AIFACTORY_DISCOVERY_SIGNAL_TTL_DAYS", "30"))
        self.signal_max_rows = int(os.environ.get("AIFACTORY_DISCOVERY_SIGNAL_MAX_ROWS", "5000"))
        self._sources = {
            "hn": SourceRuntime("hn", min_interval_sec=0.8, max_backoff_sec=120.0),
            "reddit": SourceRuntime("reddit", min_interval_sec=1.0, max_backoff_sec=120.0),
            "github": SourceRuntime("github", min_interval_sec=1.2, max_backoff_sec=180.0),
            "producthunt": SourceRuntime("producthunt", min_interval_sec=0.5, max_backoff_sec=90.0),
            "g2": SourceRuntime("g2", min_interval_sec=0.5, max_backoff_sec=90.0),
            "stackoverflow": SourceRuntime("stackoverflow", min_interval_sec=0.5, max_backoff_sec=90.0),
        }
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _save_source_health(self) -> None:
        payload = {
            "generated_at": int(time.time()),
            "sources": {name: rt.to_health() for name, rt in self._sources.items()},
        }
        self.source_health_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _with_source_runtime(
        self,
        source: str,
        fetcher: Any,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, str]]:
        rt = self._sources.get(source) or SourceRuntime(source)
        self._sources[source] = rt
        now = time.time()
        ok, reason = rt.can_call(now)
        if not ok:
            logger.info("Skipping source '%s' call: %s", source, reason)
            return []
        started = time.time()
        try:
            out = fetcher(*args, **kwargs)
            latency = int((time.time() - started) * 1000)
            rt.mark_call(time.time(), latency)
            rt.mark_success()
            return out or []
        except Exception as exc:
            latency = int((time.time() - started) * 1000)
            rt.mark_call(time.time(), latency)
            rt.mark_failure(time.time(), str(exc))
            logger.warning("Source '%s' failed: %s", source, exc)
            return []

    def _read_all_signals(self) -> list[dict[str, Any]]:
        if not self.signals_db.exists():
            return []
        try:
            return [json.loads(x) for x in self.signals_db.read_text(encoding="utf-8").splitlines() if x.strip()]
        except Exception:
            return []

    def prune_signals(self) -> dict[str, int]:
        rows = self._read_all_signals()
        if not rows:
            return {"before": 0, "after": 0, "removed": 0}
        now = int(time.time())
        cutoff = now - self.signal_ttl_days * 86400
        filtered = [r for r in rows if int(r.get("timestamp", 0)) >= cutoff]
        if len(filtered) > self.signal_max_rows:
            filtered = filtered[-self.signal_max_rows :]
        removed = len(rows) - len(filtered)
        if removed > 0:
            self.signals_db.write_text(
                "\n".join(json.dumps(x, ensure_ascii=False) for x in filtered) + ("\n" if filtered else ""),
                encoding="utf-8",
            )
        return {"before": len(rows), "after": len(filtered), "removed": max(0, removed)}

    def collect_signals(self) -> list[dict[str, Any]]:
        source_queries = [
            ("hn", "startup software pain point workflow"),
            ("reddit", "startup software pain point complaint"),
            ("producthunt", "site:producthunt.com new SaaS launch changelog"),
            ("github", "developer tools workflow pain"),
            ("g2", "site:g2.com review annoying missing feature software"),
            ("stackoverflow", "site:stackoverflow.com question recurring issue tool"),
        ]
        now = int(time.time())
        fresh: list[dict[str, Any]] = []
        existing_keys = set()
        if self.signals_db.exists():
            try:
                for line in self.signals_db.read_text(encoding="utf-8").splitlines():
                    row = json.loads(line)
                    existing_keys.add((row.get("source"), row.get("url")))
            except Exception:
                existing_keys = set()
        for source, query in source_queries:
            hits: list[dict[str, str]] = []
            if source == "hn":
                hits.extend(self._with_source_runtime("hn", _hn_search, query, 10))
                if len(hits) < 4:
                    hits.extend(_duckduckgo_search("site:news.ycombinator.com " + query, max_results=8))
            elif source == "reddit":
                # Prefer native Reddit feed; fallback to web search for broader recall.
                hits.extend(self._with_source_runtime("reddit", _reddit_search, query, 8))
                if len(hits) < 4:
                    hits.extend(_duckduckgo_search("site:reddit.com " + query, max_results=8))
            elif source == "github":
                hits.extend(self._with_source_runtime("github", _github_repo_search, query, 10))
                if len(hits) < 4:
                    hits.extend(_duckduckgo_search("site:github.com " + query, max_results=8))
            else:
                hits = self._with_source_runtime(source, _duckduckgo_search, query, 6)
            for hit in hits:
                key = (source, hit.get("url"))
                if key in existing_keys:
                    continue
                text = f"{hit.get('title','')} {hit.get('snippet','')}".lower()
                sentiment = "negative" if any(
                    k in text for k in ("problem", "pain", "issue", "missing", "frustrat", "slow", "expensive")
                ) else "neutral"
                urgency = 9 if "outage" in text else (7 if "urgent" in text else 5)
                signal = {
                    "source": source,
                    "signal_type": "pain_or_trend",
                    "timestamp": now,
                    "title": hit.get("title", ""),
                    "snippet": hit.get("snippet", ""),
                    "url": hit.get("url", ""),
                    "sentiment": sentiment,
                    "urgency": urgency,
                }
                fresh.append(signal)
                existing_keys.add(key)
        if fresh:
            with self.signals_db.open("a", encoding="utf-8") as f:
                for row in fresh:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._save_source_health()
        return fresh

    async def _simulate_problem_interviews(self, idea: str, category: str) -> list[dict[str, Any]]:
        prompt = f"""Run a lean startup problem interview simulation for this product concept.
Idea: {idea}
Category: {category}

Return strict JSON:
{{
  "interviews": [
    {{
      "persona": "who this is",
      "current_workaround": "how they solve now",
      "pain_score_0_10": 0-10,
      "willingness_to_pay_score_0_10": 0-10,
      "quoted_objection": "single line objection",
      "adoption_trigger": "single line"
    }}
  ]
}}
Use 3-5 interviews. JSON only."""
        cfg = GenerationConfig(temperature=0.25, max_tokens=1200, timeout_sec=90.0)
        text = await self.router.generate(prompt, task_type="market_research", config=cfg)
        parsed = _safe_json(text)
        interviews = parsed.get("interviews")
        if not isinstance(interviews, list):
            return []
        out = []
        for x in interviews[:6]:
            if not isinstance(x, dict):
                continue
            out.append(
                {
                    "persona": str(x.get("persona") or "")[:120],
                    "current_workaround": str(x.get("current_workaround") or "")[:240],
                    "pain_score_0_10": _clamp(float(x.get("pain_score_0_10", 0))),
                    "willingness_to_pay_score_0_10": _clamp(float(x.get("willingness_to_pay_score_0_10", 0))),
                    "quoted_objection": str(x.get("quoted_objection") or "")[:280],
                    "adoption_trigger": str(x.get("adoption_trigger") or "")[:180],
                }
            )
        return out

    async def _competitive_gap_analysis(
        self, idea: str, category: str, signals: list[dict[str, Any]]
    ) -> dict[str, Any]:
        signal_pack = "\n".join(
            f"- {s.get('title','')}: {s.get('snippet','')[:180]}" for s in signals[:24]
        )
        prompt = f"""Perform need-depth analysis for the opportunity.
Idea: {idea}
Category: {category}
Signals:
{signal_pack}

Return strict JSON:
{{
  "competitors": ["name1", "name2", "name3"],
  "gaps": [
    {{
      "gap": "what is not solved well",
      "severity_0_10": 0-10,
      "evidence": "evidence line"
    }}
  ],
  "tam_sam_som": {{
    "tam_usd_m": number,
    "sam_usd_m": number,
    "som_usd_m": number
  }},
  "pain_to_feature_map": [
    {{
      "pain": "pain",
      "feature": "feature response",
      "priority": "high|medium|low"
    }}
  ]
}}
JSON only."""
        cfg = GenerationConfig(temperature=0.2, max_tokens=1400, timeout_sec=90.0)
        text = await self.router.generate(prompt, task_type="market_research", config=cfg)
        parsed = _safe_json(text)
        return {
            "competitors": [str(x) for x in (parsed.get("competitors") or [])][:8],
            "gaps": [x for x in (parsed.get("gaps") or []) if isinstance(x, dict)][:8],
            "tam_sam_som": parsed.get("tam_sam_som") if isinstance(parsed.get("tam_sam_som"), dict) else {},
            "pain_to_feature_map": [x for x in (parsed.get("pain_to_feature_map") or []) if isinstance(x, dict)][:12],
        }

    async def _extract_candidate_ideas(
        self, signals: list[dict[str, Any]], existing_ideas: list[str], existing_categories: list[str]
    ) -> list[dict[str, Any]]:
        snippets = "\n".join(
            f"- [{s['source']}] {s.get('title','')}: {s.get('snippet','')[:220]}"
            for s in signals[:80]
        )
        duplicates = "\n".join(f"- {i[:200]}" for i in existing_ideas[-20:]) if existing_ideas else "(none)"
        prompt = f"""You are an Opportunity Scanner + Need Validator.
Use these external market signals to propose 3-5 candidate product opportunities.

Signals:
{snippets}

Existing ideas to avoid duplicating:
{duplicates}

Return strict JSON:
{{
  "ideas": [
    {{
      "idea": "one sentence product brief",
      "research_summary": "2-4 sentences with evidence from signals",
      "market_rationale": "who buys first and why now",
      "category": "one slug from {", ".join(MARKETPLACE_CATEGORY_IDS)}",
      "tags": ["4-8 tags"],
      "score_inputs": {{
        "tam": 0-10,
        "pain_severity": 0-10,
        "differentiation": 0-10,
        "feasibility": 0-10,
        "strategic_fit": 0-10,
        "evidence_strength": 0-10,
        "implementation_effort_inverse": 0-10,
        "full_software_potential": 0-10
      }},
      "validation_notes": ["3-6 short bullets"]
    }}
  ]
}}
JSON only."""
        cfg = GenerationConfig(
            temperature=0.35,
            max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
            timeout_sec=120.0,
        )
        text = await self.router.generate(prompt, task_type="market_research", config=cfg)
        parsed = _safe_json(text)
        ideas = parsed.get("ideas") if isinstance(parsed.get("ideas"), list) else []
        norm: list[dict[str, Any]] = []
        for row in ideas:
            if not isinstance(row, dict):
                continue
            idea = str(row.get("idea") or "").strip()
            if len(idea) < 24:
                continue
            category = _pick_category(row.get("category"), existing_categories)
            tags_raw = row.get("tags") or []
            tags = [str(x).strip().lower().replace(" ", "-") for x in tags_raw if str(x).strip()][:10]
            if not tags:
                tags = [category, "validated-opportunity"]
            inputs = row.get("score_inputs") if isinstance(row.get("score_inputs"), dict) else {}
            metrics = {k: _clamp(float(inputs.get(k, 0.0))) for k in (
                "tam",
                "pain_severity",
                "differentiation",
                "feasibility",
                "strategic_fit",
                "evidence_strength",
                "implementation_effort_inverse",
                "full_software_potential",
            )}
            if metrics.get("full_software_potential", 0.0) < 0.5:
                metrics["full_software_potential"] = _heuristic_full_software_potential(idea)
            scored = compute_idea_score(
                metrics,
                data_root=self.data_dir,
                category=category,
            )
            interviews = await self._simulate_problem_interviews(idea=idea[:400], category=category)
            gap_analysis = await self._competitive_gap_analysis(
                idea=idea[:400],
                category=category,
                signals=signals[:60],
            )
            norm.append(
                {
                    "idea": idea[:2000],
                    "research_summary": str(row.get("research_summary") or "")[:4000],
                    "market_rationale": str(row.get("market_rationale") or "")[:4000],
                    "category": category,
                    "tags": tags,
                    "validation_notes": [str(x) for x in (row.get("validation_notes") or [])][:8],
                    "score_inputs": metrics,
                    "score_total": scored["total"],
                    "score_confidence": scored["confidence"],
                    "problem_interviews": interviews,
                    "need_depth_analysis": gap_analysis,
                }
            )
        return norm

    def _fallback_candidate(self, signals: list[dict[str, Any]], existing_categories: list[str]) -> dict[str, Any]:
        blob = " ".join(f"{s.get('title','')} {s.get('snippet','')}" for s in signals[:20]).lower()
        category = "devtools" if any(k in blob for k in ("developer", "github", "cli", "debug")) else _pick_category(
            None, existing_categories
        )
        metrics = {
            "tam": 5.5,
            "pain_severity": 7.0,
            "differentiation": 5.0,
            "feasibility": 7.5,
            "strategic_fit": 6.0,
            "evidence_strength": 4.0,
            "implementation_effort_inverse": 7.0,
            "full_software_potential": 6.5,
        }
        scored = compute_idea_score(metrics, data_root=self.data_dir, category=category)
        return {
            "idea": "Build a focused workflow assistant that eliminates a repeatedly reported manual bottleneck from recent community pain signals.",
            "research_summary": "Discovery fallback used because candidate extraction was incomplete; signals still indicate recurring workflow friction and unmet automation demand.",
            "market_rationale": "Early adopters are small product/engineering teams that currently stitch multiple tools and pay for saved operator time.",
            "category": category,
            "tags": [category, "workflow-automation", "discovery-fallback"],
            "validation_notes": ["fallback_mode", "needs_manual_review"],
            "score_inputs": metrics,
            "score_total": scored["total"],
            "score_confidence": scored["confidence"],
            "problem_interviews": [],
            "need_depth_analysis": {},
        }

    def _rebalance_ranked_ideas(
        self, ranked: list[dict[str, Any]], existing_categories: list[str]
    ) -> list[dict[str, Any]]:
        if not ranked:
            return ranked
        counts = {k: 0 for k in MARKETPLACE_CATEGORY_IDS}
        for c in existing_categories:
            m = slug_to_marketplace_category(c)
            if m in counts:
                counts[m] += 1
        if not counts:
            return ranked
        least = min(counts.values())
        most = max(counts.values())
        out: list[dict[str, Any]] = []
        for item in ranked:
            category = slug_to_marketplace_category(item.get("category")) or "saas"
            imbalance = counts.get(category, 0)
            balance_bonus = 0.0
            if imbalance == least:
                balance_bonus = 1.25
            elif imbalance == most and most > least:
                balance_bonus = -0.75
            row = dict(item)
            row["balanced_score"] = round(float(item.get("score_total", 0.0)) + balance_bonus, 3)
            out.append(row)
        out.sort(
            key=lambda x: (float(x.get("balanced_score", 0.0)), float(x.get("score_confidence", 0.0))),
            reverse=True,
        )
        return out

    def _build_weekly_digest(self, signals: list[dict[str, Any]], ranked: list[dict[str, Any]]) -> str:
        by_source: dict[str, int] = {}
        neg = 0
        for s in signals:
            by_source[s.get("source", "unknown")] = by_source.get(s.get("source", "unknown"), 0) + 1
            if s.get("sentiment") == "negative":
                neg += 1
        top = ranked[0] if ranked else {}
        lines = [
            "# Weekly Intelligence Digest",
            "",
            f"- Generated at: {int(time.time())}",
            f"- Signals processed: {len(signals)}",
            f"- Negative/problem signals: {neg}",
            f"- Source split: {json.dumps(by_source, ensure_ascii=False)}",
            "",
            "## Top Opportunity",
            f"- Idea: {top.get('idea', '(none)')}",
            f"- Category: {top.get('category', '(none)')}",
            f"- Score: {top.get('score_total', 0):.3f} / 10",
            "",
        ]
        return "\n".join(lines)

    def _load_previous_top_score(self) -> float | None:
        if not self.ranked_ideas_file.exists():
            return None
        try:
            data = json.loads(self.ranked_ideas_file.read_text(encoding="utf-8"))
            ranked = data.get("ranked_ideas") if isinstance(data, dict) else None
            if not isinstance(ranked, list) or not ranked:
                return None
            return float(ranked[0].get("score_total"))
        except Exception:
            return None

    async def run(self, existing_ideas: list[str], existing_categories: list[str]) -> dict[str, Any]:
        prune_stats = self.prune_signals()
        new_signals = self.collect_signals()
        all_signals: list[dict[str, Any]] = self._read_all_signals()
        candidates = await self._extract_candidate_ideas(all_signals[-180:], existing_ideas, existing_categories)
        if not candidates:
            candidates = [self._fallback_candidate(all_signals[-180:], existing_categories)]
        ranked = sorted(
            candidates,
            key=lambda x: (float(x.get("score_total", 0.0)), float(x.get("score_confidence", 0.0))),
            reverse=True,
        )
        ranked = self._rebalance_ranked_ideas(ranked, existing_categories=existing_categories)
        prev_top = self._load_previous_top_score()
        top_score = float(ranked[0].get("score_total", 0.0))
        anomaly = None
        if prev_top is not None and abs(top_score - prev_top) >= 2.5:
            anomaly = {
                "type": "top_score_shift",
                "previous": prev_top,
                "current": top_score,
                "delta": round(top_score - prev_top, 3),
            }
        payload = {
            "generated_at": int(time.time()),
            "signals_collected_now": len(new_signals),
            "signals_total": len(all_signals),
            "signal_pruning": prune_stats,
            "source_health_file": str(self.source_health_file),
            "ranked_ideas": ranked[:12],
            "anomaly": anomaly,
        }
        self.ranked_ideas_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.weekly_digest_file.write_text(
            self._build_weekly_digest(all_signals[-500:], ranked),
            encoding="utf-8",
        )
        return payload
