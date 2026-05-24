#!/usr/bin/env python3
"""Render Local Security Audit UI mockups for README gallery (1440x900)."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "desktop-integrations/local-security-audit/docs/screens"

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #0f1419; color: #e7ecf3; }
.shell { display: flex; min-height: 900px; }
.sidebar { width: 220px; background: #151b23; border-right: 1px solid #243044; padding: 20px 12px; }
.logo { font-weight: 700; font-size: 15px; margin-bottom: 24px; color: #7dd3fc; }
.nav { list-style: none; }
.nav li { padding: 10px 12px; border-radius: 8px; margin-bottom: 4px; color: #94a3b8; font-size: 14px; }
.nav li.on { background: #1e3a5f; color: #e0f2fe; }
.main { flex: 1; padding: 28px 32px; }
h1 { font-size: 22px; margin-bottom: 6px; }
.sub { color: #94a3b8; font-size: 14px; margin-bottom: 24px; }
.cards { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; margin-bottom: 24px; }
.card { background: #151b23; border: 1px solid #243044; border-radius: 12px; padding: 18px; }
.label { color: #94a3b8; font-size: 12px; text-transform: uppercase; }
.value { font-size: 28px; font-weight: 700; margin-top: 6px; }
.red { color: #f87171; } .amber { color: #fbbf24; } .green { color: #34d399; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 12px 14px; border-bottom: 1px solid #243044; }
th { color: #94a3b8; font-size: 12px; text-transform: uppercase; }
.pill { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.pill.critical { background: #450a0a; color: #fca5a5; }
.pill.high { background: #451a03; color: #fdba74; }
.pill.medium { background: #422006; color: #fcd34d; }
.pill.ok { background: #0c4a6e; color: #7dd3fc; }
.panel { background: #151b23; border: 1px solid #243044; border-radius: 12px; padding: 18px; margin-bottom: 12px; }
.row { display: flex; gap: 16px; }
.code { font-family: ui-monospace, monospace; font-size: 13px; line-height: 1.5; background: #0b0f14;
  border-radius: 8px; padding: 14px; margin-top: 12px; color: #cbd5e1; }
.hl { background: #450a0a; color: #fecaca; }
.btn { display: inline-block; background: #0284c7; color: #fff; padding: 8px 14px; border-radius: 8px;
  font-size: 13px; font-weight: 600; margin-top: 12px; }
.econ { background: rgba(56,189,248,.12); border: 1px solid #1e3a5f; padding: 10px 14px;
  border-radius: 8px; font-size: 13px; margin-bottom: 20px; }
input { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #243044; background: #0b0f14; color: #e7ecf3; }
.bar { height: 8px; background: #243044; border-radius: 4px; margin-top: 8px; overflow: hidden; }
.bar i { display: block; height: 100%; width: 78%; background: linear-gradient(90deg,#38bdf8,#6366f1); }
"""

NAV = ["Dashboard", "Scan Results", "Marketplace", "Settings"]


def html(active: str, body: str) -> str:
    nav = "".join(
        f'<li class="{"on" if label == active else ""}">{label}</li>' for label in NAV
    )
    return (
        "<!DOCTYPE html><html><head><meta charset=utf-8>"
        f"<style>{CSS}</style></head><body>"
        '<div class="shell"><aside class="sidebar">'
        '<div class="logo">Local Security Audit</div>'
        f'<ul class="nav">{nav}</ul></aside>'
        f'<main class="main">{body}</main></div></body></html>'
    )


BODIES: dict[str, tuple[str, str]] = {
    "dashboard.png": (
        "Dashboard",
        """
<h1>Dashboard</h1><p class="sub">Scan local git repos — code never leaves this device.</p>
<div class="econ">AI Market · hub.aicom.io · channel $4.20 · TEE verify on</div>
<div class="cards">
  <div class="card"><div class="label">Repos scanned</div><div class="value">12</div></div>
  <div class="card"><div class="label">Critical findings</div><div class="value red">3</div></div>
  <div class="card"><div class="label">Rules cached</div><div class="value green">847</div></div>
</div>
<div class="panel"><strong>Recent scans</strong><table>
<tr><th>Repository</th><th>Branch</th><th>Findings</th><th>Last scan</th></tr>
<tr><td>aicom-factory</td><td>main</td><td><span class="pill critical">2 critical</span></td><td>2 min ago</td></tr>
<tr><td>payments-api</td><td>release/2.4</td><td><span class="pill high">5 high</span></td><td>Today 09:14</td></tr>
<tr><td>mobile-client</td><td>develop</td><td><span class="pill ok">clean</span></td><td>Yesterday</td></tr>
</table><span class="btn">+ Scan repository</span></div>
""",
    ),
    "results.png": (
        "Scan Results",
        """
<h1>Scan Results — aicom-factory</h1><p class="sub">1,284 commits · 847 files · 42s</p>
<div class="cards"><div class="card"><div class="label">Critical</div><div class="value red">2</div></div>
<div class="card"><div class="label">High</div><div class="value amber">7</div></div>
<div class="card"><div class="label">Medium / Low</div><div class="value">14</div></div></div>
<div class="panel"><table><tr><th>Severity</th><th>Finding</th><th>File</th></tr>
<tr><td><span class="pill critical">CRITICAL</span></td><td>AWS access key</td><td>scripts/deploy.sh:41</td></tr>
<tr><td><span class="pill high">HIGH</span></td><td>CVE-2024-38816</td><td>pom.xml</td></tr></table></div></div></div>""",
    ),
    "marketplace.png": (
        "Marketplace",
        """
<h1>Marketplace Feeds</h1><p class="sub">Discover, channel, invoke, cache locally</p>
<div class="panel"><input placeholder="Intent: npm CVE feed Q2 2026"></div>
<div class="panel"><strong>CVE NVD Feed — npm Q2 2026</strong><br><span style="color:#94a3b8;font-size:13px">SecIntel · trust 94% · $0.12/call</span><div class="bar"><i></i></div><span class="btn">Open channel</span></div>
<div class="panel"><strong>Secret Scanner Rules v3</strong><br><span style="color:#94a3b8;font-size:13px">PatternForge · $0.08/call</span></div>""",
    ),
    "secret-found.png": (
        "Scan Results",
        """
<h1>Secret Found</h1><p class="sub">scripts/deploy.sh · line 41 · secret-scan-v3</p>
<div class="row"><div class="panel"><span class="pill critical">CRITICAL</span><h2 style="font-size:16px;margin:12px 0">AWS Access Key exposed</h2>
<div class="code">export <span class="hl">AWS_ACCESS_KEY_ID=AKIA4EXAMPLE</span></div><span class="btn">Publish signature</span></div>
<div class="panel"><strong>Remediation</strong><ul style="margin-top:12px;padding-left:18px"><li>Rotate key</li><li>Use vault</li></ul></div></div>""",
    ),
    "deps.png": (
        "Scan Results",
        """
<h1>Dependency Tree</h1><p class="sub">payments-api · 142 direct deps</p>
<div class="panel"><table><tr><th>Package</th><th>Version</th><th>CVE</th><th>Severity</th></tr>
<tr><td>spring-core</td><td>5.3.18</td><td>CVE-2024-38816</td><td><span class="pill high">HIGH</span></td></tr>
<tr><td>lodash</td><td>4.17.19</td><td>CVE-2020-8203</td><td><span class="pill medium">MEDIUM</span></td></tr></table></div>""",
    ),
    "settings.png": (
        "Settings",
        """
<h1>Settings</h1><p class="sub">Hub wallet, cache, privacy</p>
<div class="panel"><strong>AI Market</strong><p style="color:#94a3b8;margin:8px 0;font-size:13px">hub.aicom.io · $4.20 channel</p><span class="btn">Add $5</span></div>
<div class="panel"><strong>Privacy</strong><p style="color:#94a3b8;margin:8px 0;font-size:13px">Never upload source code</p></div>""",
    ),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for name, (active, body) in BODIES.items():
            body = body.replace("<motion ", "<div ").replace("</motion>", "</div>")
            page.set_content(html(active, body), wait_until="networkidle")
            page.screenshot(path=str(OUT / name))
            print("saved", OUT / name)
        browser.close()


if __name__ == "__main__":
    main()
