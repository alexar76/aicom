"""
Reference FastAPI service bundle for full_software-style outputs.

Treat this as a structural baseline (health + REST-ish CRUD), not production auth.
Replace in-memory store with your DB and wire real JWT/session auth.

HTML/CSS aligned with factory visual-quality heuristics: design tokens on :root,
loading/empty/toast patterns, focus-visible, responsive nav toggle, labeled forms.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Generated Service Template", version="0.1.0")

# Tokens + patterns expected by web.backend.services.visual_quality_heuristics (app-like surfaces).
_PAGE_STYLE = """
<style>
  :root {
    --color-bg: #0f172a;
    --color-surface: #1e293b;
    --color-text: #e2e8f0;
    --color-muted: #94a3b8;
    --color-accent: #93c5fd;
    --color-accent-solid: #6366f1;
    --color-border: #334155;
    --radius: 0.75rem;
    --font: ui-sans-serif, system-ui, sans-serif;
  }
  :focus-visible {
    outline: 2px solid var(--color-accent-solid);
    outline-offset: 2px;
  }
  body {
    margin: 0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    font-family: var(--font);
    background: var(--color-bg);
    color: var(--color-text);
  }
  .site-header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 1rem 1.25rem;
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
  }
  .brand { font-weight: 700; }
  #nav-toggle {
    display: none;
    background: var(--color-accent-solid);
    color: #fff;
    border: none;
    padding: 0.4rem 0.65rem;
    border-radius: 0.5rem;
    cursor: pointer;
    font-weight: 600;
  }
  .site-nav a {
    color: var(--color-accent);
    margin-right: 1rem;
    text-decoration: none;
    font-size: 0.875rem;
  }
  main#main {
    flex: 1;
    padding: 1.5rem;
    max-width: 960px;
    width: 100%;
    margin: 0 auto;
    box-sizing: border-box;
  }
  .card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    padding: 1rem;
    margin-bottom: 1rem;
  }
  h1 { font-size: 1.25rem; margin: 0 0 0.5rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  th, td { border-bottom: 1px solid var(--color-border); padding: 0.5rem 0.25rem; text-align: left; }
  button.primary {
    background: var(--color-accent-solid);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    cursor: pointer;
    font-weight: 600;
  }
  input {
    width: 100%;
    padding: 0.5rem;
    border-radius: 0.5rem;
    border: 1px solid #475569;
    background: var(--color-bg);
    color: var(--color-text);
    box-sizing: border-box;
  }
  label { display: block; font-size: 0.75rem; color: var(--color-muted); margin-bottom: 0.25rem; }
  .row { display: grid; gap: 0.75rem; }
  .skeleton.skeleton-pulse {
    animation: refpulse 1.2s ease-in-out infinite;
    background: var(--color-border);
    border-radius: var(--radius);
  }
  @keyframes refpulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.45; }
  }
  .empty-state { padding: 0.75rem 0; }
  .toast-host { min-height: 0.5rem; font-size: 0.75rem; color: var(--color-muted); }
  @media (min-width: 640px) {
    .row.cols-2 { grid-template-columns: 1fr 1fr; }
  }
  @media (max-width: 640px) {
    #nav-toggle { display: inline-block; }
    .site-nav {
      display: none;
      flex-direction: column;
      width: 100%;
      padding-top: 0.5rem;
    }
    .site-nav.is-open { display: flex; }
  }
</style>
"""

_PAGE_SCRIPT = """
<script>
(function () {
  var b = document.getElementById("nav-toggle");
  var n = document.getElementById("site-nav");
  if (!b || !n) return;
  b.addEventListener("click", function () {
    var open = n.classList.toggle("is-open");
    b.setAttribute("aria-expanded", open ? "true" : "false");
  });
})();
</script>
"""


def _shell(title: str, inner: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
{_PAGE_STYLE}
<title>{title}</title>
</head>
<body>
<header class="site-header">
  <strong class="brand">Demo SaaS</strong>
  <button type="button" id="nav-toggle" aria-expanded="false" aria-label="Open navigation menu">☰</button>
  <nav id="site-nav" class="site-nav" aria-label="Primary">
    <a href="/">Dashboard</a>
    <a href="/tasks">Tasks</a>
    <a href="/settings">Settings</a>
    <a href="/login">Login</a>
  </nav>
</header>
<main id="main">{inner}</main>
{_PAGE_SCRIPT}
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def page_dashboard():
    inner = """
<h1>Dashboard</h1>
<div class="skeleton skeleton-pulse" aria-busy="true" style="height:2.5rem;margin-bottom:1rem;">Loading metrics…</div>
<section class="empty-state" data-empty="true">
  <p style="margin:0 0 .5rem;font-size:.875rem;color:var(--color-muted);">No queued deployments yet.</p>
  <button type="button" class="primary">Deploy sample</button>
</section>
<div id="toast-root" role="status" aria-live="polite" class="toast-host"></div>
<p role="alert" class="error-demo" hidden>Example validation error</p>
<div class="card row cols-2">
  <div><div style="font-size:2rem;font-weight:700;">12</div><div style="font-size:.75rem;color:var(--color-muted);">Active projects</div></div>
  <div><div style="font-size:2rem;font-weight:700;">98%</div><div style="font-size:.75rem;color:var(--color-muted);">Uptime</div></div>
</div>
<div class="card"><p style="margin:0;font-size:.875rem;line-height:1.5;">Reference UI — swap for real charts when shipping.</p></div>
"""
    return _shell("Dashboard", inner)


@app.get("/login", response_class=HTMLResponse)
def page_login():
    inner = """
<h1>Sign in</h1>
<div class="card" style="max-width:420px;">
  <div class="row">
    <div><label for="login-email">Email</label><input id="login-email" type="email" placeholder="you@company.com" autocomplete="username"/></div>
    <div><label for="login-password">Password</label><input id="login-password" type="password" placeholder="••••••••" autocomplete="current-password"/></div>
  </div>
  <div style="margin-top:1rem;"><button type="button" class="primary">Continue</button></div>
</div>
"""
    return _shell("Login", inner)


@app.get("/tasks", response_class=HTMLResponse)
def page_tasks():
    inner = """
<h1>Tasks</h1>
<div class="card">
<table><thead><tr><th>Title</th><th>Status</th></tr></thead>
<tbody>
<tr><td>Wire Postgres migrations</td><td>In progress</td></tr>
<tr><td>Add JWT refresh flow</td><td>Queued</td></tr>
<tr><td>E2E smoke on CI</td><td>Done</td></tr>
</tbody></table></div>
"""
    return _shell("Tasks", inner)


@app.get("/settings", response_class=HTMLResponse)
def page_settings():
    inner = """
<h1>Settings</h1>
<div class="card row cols-2">
  <div><label for="workspace-name">Workspace</label><input id="workspace-name" type="text" value="acme-corp"/></div>
  <div><label for="workspace-tz">Timezone</label><input id="workspace-tz" type="text" value="UTC"/></div>
</div>
<div class="card">
  <div style="font-size:.75rem;color:var(--color-muted);margin-bottom:.25rem;">Notifications</div>
  <p style="margin:0;font-size:.875rem;color:var(--color-muted);">Email digests · Slack (soon)</p>
</div>
"""
    return _shell("Settings", inner)


_ITEMS: dict[str, dict] = {}


class ItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field("", max_length=8000)


class ItemPatch(BaseModel):
    title: str | None = Field(None, max_length=500)
    description: str | None = Field(None, max_length=8000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/items")
def list_items():
    return {"items": list(_ITEMS.values()), "count": len(_ITEMS)}


@app.post("/api/items")
def create_item(body: ItemCreate):
    iid = f"item-{uuid4().hex[:12]}"
    row = {"id": iid, "title": body.title, "description": body.description}
    _ITEMS[iid] = row
    return {"item": row}


@app.patch("/api/items/{item_id}")
def patch_item(item_id: str, body: ItemPatch):
    if item_id not in _ITEMS:
        raise HTTPException(status_code=404, detail="Not found")
    if body.title is None and body.description is None:
        raise HTTPException(status_code=400, detail="Provide title and/or description")
    cur = _ITEMS[item_id]
    if body.title is not None:
        cur["title"] = body.title.strip()
    if body.description is not None:
        cur["description"] = body.description.strip()
    return {"item": cur}


@app.delete("/api/items/{item_id}")
def delete_item(item_id: str):
    if item_id not in _ITEMS:
        raise HTTPException(status_code=404, detail="Not found")
    del _ITEMS[item_id]
    return {"ok": True, "id": item_id}
