#!/usr/bin/env python3
"""
Idempotent demo products for Docker / SQLite: storefront listings + sandbox HTML.

Creates several COMPLETED rows with on-disk specs, marketing, code manifests,
and admin_force_list so the home page “Marketing landing pages” and “Full products”
sections are populated without running the LLM pipeline.

Run inside the app container **only when explicitly enabled** (does not run in production by default):

    AIFACTORY_SEED_MARKETPLACE_DEMO=1 docker compose exec -T app \\
      env AIFACTORY_SEED_MARKETPLACE_DEMO=1 python3 /app/scripts/seed_marketplace_demo.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = Path("/app/data")


def _landing_html(title: str, accent: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    body {{ margin:0;font-family:system-ui,sans-serif;background:#0c1222;color:#e2e8f0; }}
    nav {{ display:flex;gap:1.5rem;padding:1rem 2rem;background:rgba(15,23,42,.9);border-bottom:1px solid rgba(99,102,241,.25); }}
    nav a {{ color:#c7d2fe;text-decoration:none;font-weight:500; }}
    .hero {{ padding:4rem 2rem 3rem;text-align:center;background:radial-gradient(ellipse at top,{accent}22,transparent 55%); }}
    .hero h1 {{ font-size:2rem;margin:0 0 1rem;color:#fff; }}
    .cta {{ display:inline-block;margin-top:1.5rem;padding:.85rem 1.75rem;background:{accent};color:#fff;border-radius:999px;font-weight:600;text-decoration:none; }}
    section {{ padding:3rem 2rem;max-width:52rem;margin:0 auto; }}
    section h2 {{ color:#a5b4fc;margin-top:0; }}
    .grid {{ display:grid;gap:1rem; }}
    @media(min-width:640px){{ .grid {{ grid-template-columns:1fr 1fr; }} }}
    .card {{ padding:1rem 1.25rem;border-radius:12px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08); }}
    footer {{ padding:2rem;text-align:center;color:#64748b;font-size:.875rem;border-top:1px solid rgba(255,255,255,.06); }}
  </style>
</head>
<body>
  <nav>
    <a href="#how">How it works</a>
    <a href="#features">Features</a>
    <a href="#pricing">Pricing</a>
  </nav>
  <header class="hero" id="how">
    <h1>{title}</h1>
    <p style="max-width:36rem;margin:0 auto;line-height:1.6;color:#94a3b8;">
      Ship a credible one-page story: hero, proof points, and a single conversion path — generated as static HTML for instant sandbox preview.
    </p>
    <a class="cta" href="#pricing">Start free trial</a>
  </header>
  <section id="features">
    <h2>Why teams use this layout</h2>
    <div class="grid">
      <div class="card"><strong>Clear narrative</strong><p style="margin:.5rem 0 0;color:#94a3b8;font-size:.9rem;">Sections answer visitor objections in order.</p></div>
      <div class="card"><strong>Fast iteration</strong><p style="margin:.5rem 0 0;color:#94a3b8;font-size:.9rem;">Swap copy without rebuilding your backend.</p></div>
    </div>
  </section>
  <section id="pricing">
    <h2>Simple pricing</h2>
    <p style="color:#94a3b8;line-height:1.6;">Starter checklist: headline, three benefit tiles, testimonial strip, FAQ, and footer links — tuned for sharing in Slack threads.</p>
  </section>
  <footer>Preview served via AI-Factory sandbox · static marketing landing</footer>
</body>
</html>
"""


def _full_product_html(title: str, stack_line: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    body {{ margin:0;font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0; }}
    header {{ padding:2rem;border-bottom:1px solid rgba(52,211,153,.2);background:rgba(6,78,59,.25); }}
    main {{ padding:2rem;max-width:56rem;margin:0 auto; }}
    .panel {{ border-radius:12px;padding:1.25rem;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);margin-bottom:1rem; }}
    code {{ font-size:.85rem;color:#a7f3d0; }}
    h1 {{ margin:0;font-size:1.5rem; }}
    .muted {{ color:#94a3b8;font-size:.9rem;margin-top:.5rem; }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <p class="muted">{stack_line}</p>
  </header>
  <main>
    <div class="panel">
      <strong>Live demo shell</strong>
      <p class="muted">This preview bundles UI plus API-shaped stubs — representative of a full-software build from the factory pipeline.</p>
    </div>
    <div class="panel">
      <strong>Implementation snapshot</strong>
      <p><code>REST</code> handlers, persistence layer, and containerized sandbox preview ship from the same repo artifact.</p>
    </div>
  </main>
</body>
</html>
"""


DEMO_PRODUCTS: list[dict[str, Any]] = [
    {
        "id": "prod-demo-market-01",
        "idea": "E2E demo — marketplace listing + sandbox preview (Docker)",
        "taxonomy_category": "devtools",
        "delivery_profile": "marketing_landing",
        "product_name": "PulseDeck Dev Sandbox",
        "selling_description": "Reference marketing landing for storefront smoke tests — hero, features, pricing strip, and sandbox HTML preview.",
        "tags": ["demo", "devtools", "sandbox"],
        "usdt_price": 9,
        "html": lambda: _full_product_html(
            "PulseDeck Dev Sandbox",
            "FastAPI · SQLite · static dashboard shell — demo artifact for CI and investor walkthroughs.",
        ),
    },
    {
        "id": "prod-demo-landing-waitlist",
        "idea": "Marketing landing — AI scheduling assistant waitlist with pricing strip",
        "taxonomy_category": "saas",
        "delivery_profile": "marketing_landing",
        "product_name": "Caldera Waitlist One‑pager",
        "selling_description": "Neon hero, three benefit cards, social proof row, and pricing teaser — brochure HTML you can spin up from one phrase.",
        "tags": ["landing", "saas", "waitlist"],
        "usdt_price": 4.99,
        "html": lambda: _landing_html("Caldera — Join the waitlist", "#6366f1"),
    },
    {
        "id": "prod-demo-landing-studio",
        "idea": "Marketing landing — creator analytics studio promo page",
        "taxonomy_category": "productivity",
        "delivery_profile": "marketing_landing",
        "product_name": "Lensline Studio Promo",
        "selling_description": "High-contrast promo layout for a fictional creator analytics tool — sections for workflow, integrations, and CTA.",
        "tags": ["landing", "creators", "analytics"],
        "usdt_price": 4.99,
        "html": lambda: _landing_html("Lensline Studio — Ship smarter breakdowns", "#a855f7"),
    },
    {
        "id": "prod-demo-full-saas-01",
        "idea": "Marketing landing — squad CRM promo with kanban story and team invite CTA (demo UI)",
        "taxonomy_category": "saas",
        "delivery_profile": "marketing_landing",
        "product_name": "Harborline Squad CRM",
        "selling_description": "CRM promo one-pager: deals story, contacts teaser, team invites — brochure HTML for storefront demos.",
        "tags": ["saas", "crm", "kanban"],
        "usdt_price": 12,
        "html": lambda: _full_product_html(
            "Harborline Squad CRM",
            "NestJS-style API surface · relational store · dashboard shell — complexity tier above brochure landings.",
        ),
    },
    {
        "id": "prod-demo-full-iot-01",
        "idea": "Full software — facility telemetry console with device grid (demo UI)",
        "taxonomy_category": "iot",
        "delivery_profile": "full_software",
        "product_name": "RelayMesh Facility Grid",
        "selling_description": "IoT-leaning console preview: device grid language, signal health cues — illustrates heavier stacks vs. single-page landings.",
        "tags": ["iot", "telemetry", "operations"],
        "usdt_price": 14,
        "html": lambda: _full_product_html(
            "RelayMesh Facility Grid",
            "Python service layer · WebSocket-ready UX copy · sandbox packaged like a shipped ops tool.",
        ),
    },
]


def seed_product_files_sqlite(cfg: dict[str, Any], *, data_root: Path | None = None) -> None:
    """Write demo artifacts + mark COMPLETED in SQLite (no PipelineStateMachine / prometheus)."""
    import sqlite3

    root = data_root or DATA
    pid = cfg["id"]
    now = time.time()

    spec_inner = {
        "product_name": cfg["product_name"],
        "delivery_profile": cfg["delivery_profile"],
        "category": cfg["taxonomy_category"],
        "description": cfg["selling_description"],
        "core_features": [
            {"name": "Structured brief → generated artifact"},
            {"name": "Sandbox preview with relative URLs"},
            {"name": "Storefront-ready marketing metadata"},
        ],
    }
    spec_dir = root / "specs" / pid
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "specification.json").write_text(
        json.dumps({"specification": spec_inner}, indent=2),
        encoding="utf-8",
    )

    mdir = root / "state" / pid
    mdir.mkdir(parents=True, exist_ok=True)
    marketing_doc = {
        "marketing": {
            "product_name": cfg["product_name"],
            "selling_description": cfg["selling_description"],
            "category": cfg["taxonomy_category"],
            "tags": cfg["tags"],
            "monetization_scheme": {
                "paid_tiers": [
                    {
                        "name": "pro",
                        "price_usd_monthly": float(cfg["usdt_price"]),
                        "features": ["sandbox preview", "download entitlement"],
                        "target_audience": "builders",
                    }
                ]
            },
        }
    }
    (mdir / "marketing_content.json").write_text(
        json.dumps(marketing_doc, indent=2),
        encoding="utf-8",
    )
    sales_doc = {
        "sales_data": {
            "pricing": {"supported_chains": ["base"], "usdt_price": cfg["usdt_price"]},
        }
    }
    (mdir / "sales_config.json").write_text(json.dumps(sales_doc, indent=2), encoding="utf-8")

    code_dir = root / "code" / pid
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "index.html").write_text(cfg["html"](), encoding="utf-8")
    (code_dir / "code_manifest.json").write_text(
        json.dumps({"files": [{"path": "index.html"}]}, indent=2),
        encoding="utf-8",
    )

    followup_dir = root / "state" / "product_followup"
    followup_dir.mkdir(parents=True, exist_ok=True)
    (followup_dir / f"{pid}.json").write_text(
        json.dumps(
            {
                "admin_force_list": True,
                "admin_force_list_note": "Seeded demo showcase — operator showroom listing",
                "admin_force_list_at": now,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    db_path = root / "state" / "pipeline.db"
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT id FROM products WHERE id = ?", (pid,)).fetchone()
        if row:
            con.execute(
                "UPDATE products SET state = ?, idea = ?, category = ?, updated_at = ?, error = NULL WHERE id = ?",
                ("COMPLETED", cfg["idea"], cfg["taxonomy_category"], now, pid),
            )
        else:
            con.execute(
                "INSERT INTO products (id, idea, state, created_at, updated_at, category) VALUES (?,?,?,?,?,?)",
                (pid, cfg["idea"], "COMPLETED", now, now, cfg["taxonomy_category"]),
            )
        con.commit()
    finally:
        con.close()


def _write_followup(pid: str) -> None:
    d = DATA / "state" / "product_followup"
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "admin_force_list": True,
        "admin_force_list_note": "Seeded demo showcase — operator showroom listing",
        "admin_force_list_at": time.time(),
    }
    (d / f"{pid}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed_one(sm: Any, cfg: dict[str, Any]) -> None:
    from orchestrator.state_machine import PipelineState

    pid = cfg["id"]
    if pid not in sm.products:
        sm.create_product(cfg["idea"], pid)
    p = sm.products[pid]
    p.state = PipelineState.COMPLETED
    dp = cfg["delivery_profile"]
    p.metadata.setdefault("category", cfg["taxonomy_category"])
    p.metadata["delivery_profile"] = dp
    p.updated_at = time.time()
    spec_inner = {
        "product_name": cfg["product_name"],
        "delivery_profile": dp,
        "category": cfg["taxonomy_category"],
        "description": cfg["selling_description"],
        "core_features": [
            {"name": "Structured brief → generated artifact"},
            {"name": "Sandbox preview with relative URLs"},
            {"name": "Storefront-ready marketing metadata"},
        ],
    }
    spec_dir = DATA / "specs" / pid
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "specification.json").write_text(
        json.dumps({"specification": spec_inner}, indent=2),
        encoding="utf-8",
    )

    mdir = DATA / "state" / pid
    mdir.mkdir(parents=True, exist_ok=True)
    marketing_doc = {
        "marketing": {
            "product_name": cfg["product_name"],
            "selling_description": cfg["selling_description"],
            "category": cfg["taxonomy_category"],
            "tags": cfg["tags"],
            "monetization_scheme": {
                "paid_tiers": [
                    {
                        "name": "pro",
                        "price_usd_monthly": float(cfg["usdt_price"]),
                        "features": ["sandbox preview", "download entitlement"],
                        "target_audience": "builders",
                    }
                ]
            },
        }
    }
    (mdir / "marketing_content.json").write_text(
        json.dumps(marketing_doc, indent=2),
        encoding="utf-8",
    )

    sales_doc = {
        "sales_data": {
            "pricing": {"supported_chains": ["base"], "usdt_price": cfg["usdt_price"]},
        }
    }
    (mdir / "sales_config.json").write_text(json.dumps(sales_doc, indent=2), encoding="utf-8")

    code_dir = DATA / "code" / pid
    code_dir.mkdir(parents=True, exist_ok=True)
    html_fn = cfg["html"]
    (code_dir / "index.html").write_text(html_fn(), encoding="utf-8")
    manifest = {"files": [{"path": "index.html"}]}
    (code_dir / "code_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _write_followup(pid)


def main() -> None:
    flag = os.environ.get("AIFACTORY_SEED_MARKETPLACE_DEMO", "").strip().lower()
    if flag not in ("1", "true", "yes"):
        print(
            "Skipping marketplace demo seed (set AIFACTORY_SEED_MARKETPLACE_DEMO=1 to run).",
            file=sys.stderr,
        )
        return

    os.environ.setdefault("USE_SQLITE", "true")
    os.environ.setdefault("SQLITE_PATH", str(DATA / "state" / "pipeline.db"))

    from orchestrator.state_machine import PipelineStateMachine

    sm = PipelineStateMachine(
        state_file=str(DATA / "state" / "pipeline.json"),
        use_sqlite=True,
        db_path=str(DATA / "state" / "pipeline.db"),
    )

    for cfg in DEMO_PRODUCTS:
        _seed_one(sm, cfg)

    sm._save_state()

    print(f"OK — seeded {len(DEMO_PRODUCTS)} demo products (landings + full software). Refresh / storefront.")


if __name__ == "__main__":
    main()
