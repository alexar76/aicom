#!/usr/bin/env python3
"""Replace failed prod-demo-landing-studio sandbox with a QA-ready Lensline landing."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = Path(os.environ.get("AIFACTORY_DATA_ROOT", str(ROOT / "data")))
PID = "prod-demo-landing-studio"


def landing_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="description" content="Lensline Studio — creator analytics studio for workflow insights, integrations, and audience growth."/>
  <title>Lensline Studio — Ship smarter breakdowns</title>
  <style>
    :root {
      --bg: #0c0a14;
      --surface: rgba(255,255,255,.05);
      --text: #f1f5f9;
      --muted: #94a3b8;
      --accent: #a855f7;
      --accent-2: #6366f1;
      --ring: #c4b5fd;
      --radius: 14px;
      --max: 56rem;
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, Segoe UI, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }
    a { color: #c4b5fd; }
    a:focus-visible, button:focus-visible {
      outline: 2px solid var(--ring);
      outline-offset: 3px;
    }
    nav {
      display: flex;
      flex-wrap: wrap;
      gap: 1rem 1.5rem;
      align-items: center;
      justify-content: space-between;
      padding: 1rem 1.25rem;
      border-bottom: 1px solid rgba(168,85,247,.25);
      background: rgba(12,10,20,.92);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    nav .links { display: flex; gap: 1.25rem; flex-wrap: wrap; }
    nav a { text-decoration: none; font-weight: 500; }
    .logo { font-weight: 700; color: #fff; letter-spacing: -.02em; }
    .hero {
      padding: 3.5rem 1.25rem 2.5rem;
      text-align: center;
      background: radial-gradient(ellipse 80% 60% at 50% 0%, rgba(168,85,247,.28), transparent 60%);
    }
    .hero h1 { font-size: clamp(1.75rem, 4vw, 2.5rem); margin: 0 0 .75rem; }
    .hero p { max-width: 36rem; margin: 0 auto 1.5rem; color: var(--muted); }
    .cta {
      display: inline-block;
      padding: .85rem 1.6rem;
      border-radius: 999px;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #fff;
      font-weight: 600;
      text-decoration: none;
    }
    section {
      padding: 2.5rem 1.25rem;
      max-width: var(--max);
      margin: 0 auto;
    }
    section h2 { margin: 0 0 1rem; color: #ddd6fe; font-size: 1.25rem; }
    .grid {
      display: grid;
      gap: 1rem;
    }
    @media (min-width: 640px) {
      .grid.cols-2 { grid-template-columns: 1fr 1fr; }
      .grid.cols-3 { grid-template-columns: repeat(3, 1fr); }
    }
    .card {
      padding: 1.1rem 1.25rem;
      border-radius: var(--radius);
      background: var(--surface);
      border: 1px solid rgba(255,255,255,.08);
    }
    .integrations {
      display: flex;
      flex-wrap: wrap;
      gap: .5rem;
      margin-top: .75rem;
    }
    .pill {
      font-size: .8rem;
      padding: .35rem .7rem;
      border-radius: 999px;
      background: rgba(99,102,241,.2);
      color: #e0e7ff;
    }
    footer {
      padding: 2rem 1.25rem;
      text-align: center;
      color: var(--muted);
      font-size: .875rem;
      border-top: 1px solid rgba(255,255,255,.06);
    }
  </style>
</head>
<body>
  <nav aria-label="Primary">
    <span class="logo">Lensline Studio</span>
    <div class="links">
      <a href="#workflow">Workflow</a>
      <a href="#analytics">Analytics</a>
      <a href="#integrations">Integrations</a>
      <a href="#pricing">Pricing</a>
    </div>
  </nav>
  <header class="hero" id="workflow">
    <h1>Ship smarter creator breakdowns</h1>
    <p>
      Lensline Studio is a creator analytics studio: unify your workflow, surface audience insights,
      and act on integrations-backed recommendations — one promo page, instant sandbox preview.
    </p>
    <a class="cta" href="#pricing">Start free studio trial</a>
  </header>
  <section id="analytics">
    <h2>Creator analytics that match your workflow</h2>
    <div class="grid cols-3">
      <div class="card">
        <strong>Audience pulse</strong>
        <p style="margin:.5rem 0 0;color:var(--muted);font-size:.9rem;">
          Real-time retention and revenue cues for every channel you publish on.
        </p>
      </div>
      <div class="card">
        <strong>Breakdown studio</strong>
        <p style="margin:.5rem 0 0;color:var(--muted);font-size:.9rem;">
          Compare formats, hooks, and posting windows without leaving the dashboard narrative.
        </p>
      </div>
      <div class="card">
        <strong>Actionable CTA paths</strong>
        <p style="margin:.5rem 0 0;color:var(--muted);font-size:.9rem;">
          Turn insights into the next experiment — export snapshots for your team in one click.
        </p>
      </div>
    </div>
  </section>
  <section id="integrations">
    <h2>Integrations for modern creator stacks</h2>
    <p style="color:var(--muted);max-width:40rem;">
      Connect YouTube, TikTok, Patreon, and newsletter tools. Lensline normalizes metrics so your
      workflow stays in one analytics studio instead of five browser tabs.
    </p>
    <div class="integrations" aria-label="Supported integrations">
      <span class="pill">YouTube</span>
      <span class="pill">TikTok</span>
      <span class="pill">Patreon</span>
      <span class="pill">Beehiiv</span>
      <span class="pill">Stripe</span>
    </div>
  </section>
  <section id="pricing">
    <h2>Simple studio pricing</h2>
    <div class="grid cols-2">
      <div class="card">
        <strong>Creator</strong>
        <p style="margin:.5rem 0 0;color:var(--muted);font-size:.9rem;">Workflow boards + weekly breakdowns.</p>
      </div>
      <div class="card">
        <strong>Studio Pro</strong>
        <p style="margin:.5rem 0 0;color:var(--muted);font-size:.9rem;">Integrations, team seats, and export API.</p>
      </div>
    </div>
  </section>
  <footer>Preview · Lensline Studio promo · AI-Factory marketing landing</footer>
</body>
</html>
"""


def main() -> int:
    code_dir = DATA / "code" / PID
    code_dir.mkdir(parents=True, exist_ok=True)

    for name in ("app.js", "utils.js", "style.css", "package.json", "implementation_plan.json"):
        p = code_dir / name
        if p.is_file():
            p.unlink()
    tests_dir = code_dir / "tests"
    if tests_dir.is_dir():
        import shutil

        shutil.rmtree(tests_dir)

    html = landing_html()
    (code_dir / "index.html").write_text(html, encoding="utf-8")
    manifest = {"files": [{"path": "index.html"}]}
    (code_dir / "code_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    bugs_dir = DATA / "bugs" / PID
    if bugs_dir.is_dir():
        import shutil

        shutil.rmtree(bugs_dir)

    followup_dir = DATA / "state" / "product_followup"
    followup_dir.mkdir(parents=True, exist_ok=True)
    (followup_dir / f"{PID}.json").write_text(
        json.dumps(
            {
                "admin_force_list": True,
                "admin_force_list_note": "Refreshed Lensline landing preview — operator showroom",
                "admin_force_list_at": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    import sqlite3

    db = DATA / "state" / "pipeline.db"
    now = time.time()
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT id FROM products WHERE id = ?", (PID,)).fetchone()
        if not row:
            con.execute(
                "INSERT INTO products (id, idea, state, created_at, updated_at, category) VALUES (?,?,?,?,?,?)",
                (
                    PID,
                    "Marketing landing — creator analytics studio promo page",
                    "COMPLETED",
                    now,
                    now,
                    "productivity",
                ),
            )
        else:
            con.execute(
                "UPDATE products SET state = ?, updated_at = ?, error = NULL, category = ? WHERE id = ?",
                ("COMPLETED", now, "productivity", PID),
            )
        con.commit()
    finally:
        con.close()

    print(f"OK {PID} -> COMPLETED, index.html refreshed ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
