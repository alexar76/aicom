"""Render SKOPOS documentation markdown for all 20 doc locales."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DOC_LANGS = (
    "en", "zh", "es", "hi", "ar", "pt", "ru", "ja", "fr", "de",
    "ko", "it", "tr", "id", "vi", "th", "hr", "sk", "nl", "fa",
)

_INSTALL_SH = """```bash
cd skopos
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp servers.example.yaml servers.yaml
cp agent.example.yaml agent.yaml
export SKOPOS_DASHBOARD_PASSWORD='strong-secret'
python skoposctl.py collect
python skoposctl.py security-scan
streamlit run dashboard.py
```"""

_DOCKER_SH = """```bash
docker compose up -d --build
```"""

_PG_SH = """```bash
# .env
SKOPOS_POSTGRES_USER=skopos
SKOPOS_POSTGRES_PASSWORD=change-me
SKOPOS_DATABASE_URL=postgresql://skopos:change-me@postgres:5432/skopos

docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
```"""

_Mermaid = """```mermaid
flowchart LR
  nginx[nginx access.log] -->|SSH tail| collector[skopos collector]
  collector --> db[(SQLite or PostgreSQL)]
  db --> ui[Streamlit UI]
  ui --> agent[AI agent]
  collector --> security[Security probes]
  security --> db
```"""

_SERVERS_YAML = """```yaml
servers:
  - name: factory
    source: ssh_nginx_access_log
    ssh:
      host: 203.0.113.10
      port: 22
      user: deploy
      key_path: ~/.ssh/id_rsa
    nginx:
      access_log_path: /var/log/nginx/access.log
      auto_discover_logs: true
      auto_discover_docker_logs: false
```"""

_CLI_SH = """```bash
python skoposctl.py collect
python skoposctl.py collect --full
python skoposctl.py security-scan
python skoposctl.py discover
```"""

_NGINX_FORMAT = """```nginx
log_format skopos '$remote_addr - $remote_user [$time_local] '
                  '"$request" $status $body_bytes_sent '
                  '"$http_referer" "$http_user_agent" "$host"';
access_log /var/log/nginx/access.log skopos;
```"""

_APACHE_FORMAT = """```apache
LogFormat "%h %l %u %t \\"%r\\" %>s %b \\"%{Referer}i\\" \\"%{User-Agent}i\\"" combined
CustomLog /var/log/apache2/access.log combined
```"""

_CURL_SH = """```bash
curl -sS http://127.0.0.1:8088/
curl -sS http://127.0.0.1:8088/admin/
curl -sS "http://127.0.0.1:8088/admin/?page=settings"
tail -n 5 /opt/metis/deploy/apache-test/logs/access_log
```"""


def _base_strings() -> dict[str, Any]:
    return {
        "index": {
            "title": "SKOPOS Documentation",
            "intro": "Welcome to the SKOPOS operator guide. Use the tabs above to jump between setup, deployment, configuration, and day-to-day usage.",
            "what_heading": "What SKOPOS does",
            "what_body": "SKOPOS collects **nginx access logs** from your servers over SSH, stores them in a local SQLite or PostgreSQL database, and renders analytics plus a Security Center with AI-assisted reports.",
            "links_heading": "Quick links",
            "link_task": "Task",
            "link_where": "Where",
            "links": [
                ("First-time setup", "**Quick Start** in the sidebar or top bar"),
                ("Fleet SSH & logs", "**Settings** → `servers.yaml`"),
                ("Traffic dashboards", "**Analytics** (home)"),
                ("Security scans", "**Security**"),
                ("AI agent", "Floating chat button (bottom-right)"),
            ],
            "pages_heading": "Pages at a glance",
            "pages_rows": [
                ("**Quick Start**", "Six-step wizard — server, SSH, password, collect, scan"),
                ("**Analytics**", "Traffic dashboards, AI briefing, 7 tabs (Overview → System)"),
                ("**Security**", "9 tabs — score, AI report, ports, knocks, 3D map, audit"),
                ("**Scan History**", "Timeline, trends, compare two scans, log table"),
                ("**Settings**", "Password, DB, auto-scan, Telegram, SSH keys, fleet YAML"),
                ("**Documentation**", "This guide — 20 languages, embedded screenshots"),
            ],
            "docs_note": "Open **Documentation** in the sidebar for the full operator guide with screenshots. The **Usage** tab documents every page and tab in detail.",
            "shots_heading": "Screenshots",
            "shot1": "Analytics dashboard — premium theme",
            "shot2": "Sidebar navigation and theme selector",
            "shot_note": "**Note:** Screenshots illustrate the UI; your fleet data will differ.",
        },
        "deployment": {
            "title": "Deployment",
            "req_heading": "Requirements",
            "reqs": [
                "Python **3.9+** (or Docker)",
                "SSH key access to each monitored host",
                "**nginx** writing access logs in combined or custom format",
                "Outbound HTTPS if you use cloud LLM providers (OpenRouter, OpenAI, etc.)",
            ],
            "install_heading": "Bare-metal / VM",
            "install_open": "Open `http://localhost:8501`.",
            "docker_heading": "Docker Compose",
            "docker_mount": "Mount `servers.yaml`, `agent.yaml`, and SSH keys via compose volumes (see `docker-compose.yml`).",
            "pg_heading": "PostgreSQL (production)",
            "pg_body": "For production, use PostgreSQL instead of the SQLite file:",
            "priority": "Priority: **`SKOPOS_DATABASE_URL`** env → `database_url` in `servers.yaml` → `db_path` (SQLite dev).",
            "checklist_heading": "Production checklist",
            "checklist": [
                "Set **`SKOPOS_DASHBOARD_PASSWORD`**",
                "Use **PostgreSQL** (`SKOPOS_DATABASE_URL`) for multi-user / durable prod storage",
                "Enable **`SKOPOS_SSH_STRICT_HOST_KEYS=1`**",
                "Restrict port **8501** to VPN or reverse proxy with TLS",
                "Schedule **`skoposctl.py collect`** via cron or systemd timer",
                "Enable auto-scan in **Settings** (default: every 60 minutes)",
            ],
            "arch_heading": "Architecture (high level)",
            "arch_caption": "Empty header area becomes top navigation in SKOPOS",
        },
        "configuration": {
            "title": "Configuration",
            "servers_heading": "`servers.yaml`",
            "servers_intro": "Each server entry describes SSH access and **nginx log paths**:",
            "field_col": "Field",
            "purpose_col": "Purpose",
            "server_rows": [
                ("`name`", "Label in dashboards and filters"),
                ("`source`", "`ssh_nginx_access_log` (nginx only) or `ssh_http_access_log` (nginx + optional Apache)"),
                ("`nginx.access_log_path`", "Primary access log file"),
                ("`nginx.access_log_paths`", "Extra log files (multi-site)"),
                ("`nginx.auto_discover_logs`", "Parse nginx configs on the host for more paths"),
                ("`nginx.auto_discover_docker_logs`", "Optional: also tail public Docker HTTP containers"),
            ],
            "perm_heading": "Permissions",
            "perm_body": "The SSH user must be able to **read nginx log files** (often membership in the `adm` group on Debian/Ubuntu).",
            "subdomain_heading": "Domains & subdomains (auto-discovery)",
            "subdomain_body": (
                "You don't list domains anywhere — SKOPOS groups every request by its **domain** "
                "(`host`) automatically, so each site and subdomain shows up on its own in Analytics "
                "(the **host** filter) and in threat alerts. The only requirement: the host's nginx "
                "must **log the vhost**. The stock *combined* format omits it, so add `$host` to "
                "`log_format` once and reload — no per-domain config, ever:"
            ),
            "subdomain_after": (
                "Then `sudo nginx -t && sudo nginx -s reload`. SKOPOS's parser accepts **both** the "
                "standard combined format and this `$host`-prefixed one, so existing log lines keep "
                "parsing during the switch. Add a new subdomain later? Nothing to do here — as soon "
                "as it serves traffic through the same nginx, it appears on its own. (Per-vhost "
                "`access_log` files also work: point `nginx.access_log_paths` at them or leave "
                "`auto_discover_logs: true`.)"
            ),
            "agent_heading": "`agent.yaml`",
            "agent_body": "LLM providers for the Security Report and floating agent. Default: **OpenRouter** via `OPENROUTER_API_KEY`.",
            "env_heading": "Environment variables",
            "env_rows": [
                ("`SKOPOS_DASHBOARD_PASSWORD`", "Shared dashboard password (login form); set via Settings or `.env`"),
                ("`SKOPOS_DASHBOARD_PASSWORD_MIN_LENGTH`", "Minimum length for new passwords (default **12**)"),
                ("`SKOPOS_DASHBOARD_SESSION_HOURS`", "Auto sign-out after N hours (default **12**)"),
                ("`OPENROUTER_API_KEY`", "Default LLM provider"),
                ("`SKOPOS_SSH_KEY_PASSPHRASE`", "Passphrase for encrypted SSH keys"),
                ("`SKOPOS_SSH_STRICT_HOST_KEYS`", "`1` to verify host keys"),
            ],
            "ui_heading": "Where to change things in the UI",
            "ui_rows": [
                ("Language & theme", "Sidebar bottom"),
                ("Collection / backfill", "Sidebar on **Analytics**"),
                ("Auto-scan interval", "**Settings**"),
                ("Telegram alerts", "**Settings**"),
                ("Security agent provider", "**Security** → AI Agent tab"),
            ],
            "settings_detail_heading": "Settings sections (detail)",
            "settings_detail_rows": [
                ("Dashboard access", "`SKOPOS_DASHBOARD_PASSWORD`, session hours, min length policy"),
                ("Database", "`SKOPOS_DATABASE_URL` or SQLite `db_path`; test + migrate in UI"),
                ("Auto-scan", "Background security scan interval (minutes)"),
                ("Telegram", "`SKOPOS_TELEGRAM_*` env vars; notify on new critical findings"),
                ("SSH keys", "Generate Ed25519; keys stored under `.skopos/ssh/`"),
                ("Fleet servers", "Visual editor for `servers.yaml` — nginx, Apache, docker logs"),
            ],
            "agent_detail_heading": "`agent.yaml` providers",
            "agent_detail_body": "Each provider block needs an API key env var. Default stack uses **OpenRouter** (`OPENROUTER_API_KEY`). Providers appear in Summary Report, floating agent, and Security → AI Agent tab.",
            "agent_detail_rows": [
                ("`openrouter`", "`OPENROUTER_API_KEY` — default; many models via one key"),
                ("`openai`", "`OPENAI_API_KEY`"),
                ("`anthropic`", "`ANTHROPIC_API_KEY`"),
                ("`deepseek`", "`DEEPSEEK_API_KEY`"),
            ],
            "shot_caption": "Settings and sidebar controls",
        },
        "usage": {
            "title": "Usage",
            "intro": "Complete walkthrough of every SKOPOS page, tab, and control. Screenshots show the real UI; your fleet metrics will differ.",
            "daily_heading": "Daily workflow",
            "daily_steps": [
                "Open **Analytics** — review traffic, filters, and period presets (all times in **UTC**).",
                "Read the **AI Ecosystem briefing** card for fleet health in plain language.",
                "Check the **Security Score** ring and alert banner in the sidebar.",
                "Open **Security** — score, ports, knocks, audit findings, and the **Summary Report**.",
                "Use **Scan History** to compare snapshots and spot regressions.",
                "Ask the **floating AI agent** (chat bubble, bottom-right) about alerts or hardening.",
            ],
            "shell_heading": "Global shell (every page)",
            "shell_intro": "After login, these elements appear on every page:",
            "shell_bullets": [
                "**Sidebar** — six main pages, language & theme pickers, security score ring, alert banner, auto-scan / Telegram captions, logout.",
                "**Top bar** — **Documentation**, **Quick Start**, **Settings** (left-aligned).",
                "**Alert banner** — up to five critical/high alerts with a link to **Security**.",
                "**Floating agent** — chat button bottom-right; opens on any page.",
            ],
            "shell_shot": "Sidebar — navigation, language, theme",
            "quickstart_heading": "Quick Start wizard",
            "quickstart_intro": "Sidebar → **Quick Start** or top bar. A six-step wizard for first-time setup:",
            "quickstart_steps": [
                "**Welcome** — checklist: server, SSH, password, AI key, traffic collect, security scan.",
                "**Server** — first fleet entry (name, host, user, port, nginx log path) → writes `servers.yaml`.",
                "**SSH** — generate Ed25519 key, test connection, upload public key to the host.",
                "**Security & AI** — set dashboard password, session hours, OpenRouter key, enable auto-scan.",
                "**Collect** — run first log collection from the wizard.",
                "**Scan** — run first security scan; **Done** links to Analytics, Security, Settings.",
            ],
            "quickstart_note": "You can skip the wizard anytime; **Settings** covers the same options. Incomplete setup shows a banner in the sidebar.",
            "quickstart_shot": "Quick Start — Security & AI step",
            "analytics_heading": "Analytics page",
            "analytics_intro": "Home page (`dashboard.py`). Collects nginx access logs over SSH and renders traffic dashboards.",
            "analytics_toolbar_heading": "Toolbar & sidebar controls",
            "analytics_toolbar_bullets": [
                "**Period** — presets (day / week / month / 3 months / year) or custom relative/absolute range. All chart timestamps are **UTC**.",
                "**Filters** — hide bot scans, hide internal/service traffic, external IPs only; multiselect by server, host, country; path substring.",
                "**Sidebar** — override `servers.yaml` path; **Collect now** (incremental) and **Backfill all** (full history pull).",
            ],
            "analytics_briefing_heading": "AI Ecosystem briefing",
            "analytics_briefing_bullets": [
                "Card at the top summarises fleet mood, security score, collector status, and top risks.",
                "Uses `OPENROUTER_API_KEY` when set; falls back to rule-based text otherwise.",
                "Cached ~15 minutes; click refresh to regenerate.",
            ],
            "analytics_briefing_shot": "AI Ecosystem briefing card",
            "analytics_tabs_heading": "Analytics tabs",
            "tab_overview": "Overview",
            "tab_geography": "Geography",
            "tab_audience": "Audience",
            "tab_content": "Content",
            "tab_sources": "Sources",
            "tab_journal": "Journal",
            "tab_system": "System",
            "tab_score": "Score & Alerts",
            "tab_report": "Summary Report",
            "tab_security_overview": "Overview",
            "tab_ports": "Ports",
            "tab_knocks": "Port Knocks",
            "tab_resources": "Resources",
            "tab_audit": "Audit",
            "tab_3d": "3D Threat Map",
            "tab_agent": "AI Agent (tab)",
            "security_tabs_heading": "Security tabs",
            "tab_timeline": "Timeline",
            "tab_trends": "Trends",
            "tab_compare": "Compare",
            "tab_log": "Log",
            "history_tabs_heading": "Tabs",
            "analytics_tab_overview": [
                "Traffic timeline (hour or day granularity).",
                "Country donuts — requests vs unique visitors.",
                "Top pages and hosts bar charts.",
                "Hourly heatmap (day × hour).",
                "HTTP status code distribution.",
            ],
            "analytics_tab_geography": [
                "View picker — **Overall** / **By server** / **By site**.",
                "Overall: world map, per-country bars, donuts, timelines, summary table.",
                "By server / by site: stacked countries × entity, plus a dropdown to drill into one host.",
                "Requires GeoIP (`geoip_mmdb_path` or HTTP fallback).",
            ],
            "analytics_tab_audience": [
                "Browser/client, OS, and device donuts.",
                "Top visitor IPs bar chart.",
            ],
            "analytics_tab_content": [
                "Page treemap (host → path hierarchy).",
                "Popular paths and hosts.",
                "Ecosystem segment traffic.",
            ],
            "analytics_tab_sources": [
                "Top referer domains.",
                "Direct vs referred traffic metrics.",
            ],
            "analytics_tab_journal": [
                "Visit log table — time, host, server IP, visitor IP, country, client, OS, device, method, path, status, referer (up to 1000 rows).",
            ],
            "analytics_tab_system": [
                "Per-server collector status — last OK time, rows inserted, last error.",
                "Resolved log sources (nginx files, Apache, docker container IDs).",
            ],
            "analytics_shot": "Analytics — Overview tab (premium theme)",
            "security_heading": "Security Center",
            "security_intro": "Sidebar → **Security**. SSH probes each server for ports, firewall, resources, auth logs, and Docker exposure.",
            "security_sidebar_bullets": [
                "Override `agent.yaml` path.",
                "Filter by server or **Scan all servers** (sidebar button).",
            ],
            "security_kpi_note": "KPI row: **Findings**, **Critical**, **High**, **Public ports** — fleet-wide totals for the selected filter.",
            "security_tab_score": [
                "Fleet score /100, letter grade, progress bar.",
                "Per-server score cards.",
                "Rule-based audit remarks.",
                "Expandable alert list — severity, message, remediation hint.",
            ],
            "security_tab_report": [
                "Risk badge (Critical / High / Medium / Low) and fleet score.",
                "**LLM provider** dropdown — from `agent.yaml` (default OpenRouter).",
                "**Generate AI report** — full markdown analysis; before that, a **rules preview** is shown.",
                "Metrics: total findings, critical, high, servers in report.",
                "**Download Markdown** — save the report for tickets or runbooks.",
                "Sections: executive summary, perimeter, project hardening, per-server notes.",
            ],
            "security_tab_report_shot": "Summary Report — AI security brief",
            "security_tab_overview": [
                "Multi-server fleet chart.",
                "Per-server expander: CPU / memory / load gauges, findings bar, uptime, kernel snippet.",
            ],
            "security_tab_ports": [
                "Visual port map per server.",
                "Table: protocol, port, address, bind scope, exposure (Open / Localhost / Other), process name.",
                "Raw `firewall_status` output.",
            ],
            "security_tab_knocks": [
                "KPIs: events, unique IPs, top targeted port, high-threat count.",
                "Charts: top actors, actor types, by port, countries, timeline, heatmap.",
                "Actor table — IP, country, classification, threat score, hits, ports, servers.",
                "Event log (last 300 events) — SSH probes, firewall drops, fail2ban, web scans.",
            ],
            "security_tab_resources": [
                "Per server: CPU %, memory %, load/cores % gauges; network I/O; disk usage charts.",
            ],
            "security_tab_audit": [
                "Rule-based findings per server — severity, detail, recommendation.",
                "Auth log sample when failed SSH logins detected.",
            ],
            "security_tab_3d": [
                "Fullscreen 3D threat map per server.",
                "Legend: server (center), internet (top), public ports, localhost ports, findings on outer ring.",
            ],
            "security_tab_3d_shot": "3D Threat Map",
            "security_tab_agent": [
                "One-shot **Run AI audit** (separate from the floating chat agent).",
                "Provider picker and markdown result.",
                "For ongoing Q&A use the floating agent or **Summary Report**.",
            ],
            "history_heading": "Scan History",
            "history_intro": "Sidebar → **Scan History**. Requires at least two scans for comparison features.",
            "history_sidebar_bullets": [
                "History window slider — 7 to 90 days.",
                "Server filter — all servers or one host.",
            ],
            "history_tabs": [
                ("Timeline", "Score over time, scan activity calendar, fleet radar chart."),
                ("Trends", "Findings by severity over time."),
                ("Compare", "Pick scan A vs scan B — diff chart, new issues and resolved lists."),
                ("Log", "Table — time, server, findings, critical, high counts."),
            ],
            "settings_heading": "Settings page",
            "settings_intro": "Sidebar or top bar → **Settings**. All fleet and dashboard configuration in one place.",
            "settings_sections": [
                ("Dashboard access", "Set/change/clear password, session hours, policy checklist."),
                ("Database", "SQLite vs PostgreSQL; test connection; apply URL and migrate data."),
                ("Auto-scan", "Enable toggle; interval 5–1440 minutes (default 60)."),
                ("Telegram alerts", "Enable, chat ID, bot token env, notify interval, test send after scans."),
                ("SSH keys", "Key status; generate Ed25519/RSA (opens terminal on desktop)."),
                ("Fleet servers", "Per-server expander — SSH, nginx/Apache/docker logs, test SSH, upload key, custom commands (requires `SKOPOS_ALLOW_CUSTOM_SSH_COMMANDS=1`)."),
                ("Add server / Save", "Form for new host; **Save servers.yaml** writes config + optional `.env` tokens."),
            ],
            "settings_shot": "Settings — fleet servers and save",
            "agent_heading": "Floating AI agent",
            "agent_intro": "Bottom-right chat button on every page. Multi-turn DevOps & security assistant with fleet context.",
            "agent_bullets": [
                "Provider picker (from `agent.yaml`).",
                "**Quick questions** — critical alerts, open ports, SSH hardening, port-knock summary, top recommendations.",
                "Chat history within the session; **Clear** resets the thread.",
                "Context includes posture, recent scans, traffic summary (see `agent/context.py`).",
            ],
            "agent_shot": "Floating Security Agent",
            "ai_surfaces_heading": "Three AI surfaces — when to use which",
            "ai_surfaces_rows": [
                ("**AI Ecosystem briefing** (Analytics)", "Daily fleet health paragraph; auto-refreshed."),
                ("**Summary Report** (Security → tab)", "Formal markdown remediation brief; downloadable."),
                ("**Floating agent** (every page)", "Interactive Q&A about alerts, ports, hardening."),
                ("**Security → AI Agent tab**", "One-shot full audit run; not a chat."),
            ],
            "cli_heading": "CLI",
            "topbar_heading": "Top bar",
            "topbar_body": "Header links — **Documentation**, **Quick Start**, **Settings** — for fast navigation without scrolling the sidebar.",
        },
        "nginx": {
            "title": "HTTP access logs — scope & limitations",
            "primary_note": "**Primary:** SKOPOS analytics are built for **nginx access logs**. **Apache combined** format is also supported when explicitly enabled (`apache.enabled: true`).",
            "supported_heading": "Supported",
            "source_col": "Source",
            "how_col": "How",
            "supported_rows": [
                ("nginx access log files on the host", "`ssh_nginx_access_log` or `ssh_http_access_log` + `nginx.access_log_path`"),
                ("Apache access log files (combined)", "`ssh_http_access_log` + `apache.enabled: true`"),
                ("Additional nginx logs", "`access_log_paths` or `auto_discover_logs`"),
                ("Additional Apache logs", "`apache.access_log_paths` or `apache.auto_discover_logs`"),
                ("Docker container stdout (optional)", "Only when `auto_discover_docker_logs: true`; parser tries **combined** first, then **uvicorn**"),
            ],
            "not_supported_heading": "Not supported as primary analytics",
            "not_supported": [
                "Caddy / Traefik as standalone log sources",
                "Cloud CDN logs (Cloudflare, Fastly) without combined-shaped lines",
                "Application logs that are not HTTP access lines",
            ],
            "nginx_proxy_note": "If you terminate TLS on nginx and proxy to Node/Python, **keep nginx access logging enabled** — that remains the canonical traffic record for production fleets.",
            "apache_heading": "Apache (test / secondary)",
            "apache_body": "Apache must use **combined** log format (same fields as nginx combined). Example:",
            "apache_metis": "On metis, a test httpd container can run on **port 8088** alongside nginx on 80/443 — see `metis/deploy/apache-test/`.",
            "admin_heading": "Admin panel smoke test",
            "admin_step_deploy": "Deploy: `./metis/deploy/apache-test/deploy.sh` on the metis host.",
            "admin_step_traffic": "Generate traffic:",
            "admin_step_config": "In `servers.yaml`: `source: ssh_http_access_log`, `apache.enabled: true`, path to `access_log`.",
            "admin_step_verify": "In SKOPOS **Analytics**, filter paths containing `/admin` — lines should appear after collect.",
            "admin_fixture": "The Apache admin routes are a **test fixture** for parser/filter validation; production fleets should still treat nginx access logs as canonical.",
            "rec_heading": "Recommended nginx `log_format`",
            "rec_body": "Include at least: `$remote_addr`, `$time_local`, `$request`, `$status`, `$body_bytes_sent`, `$http_referer`, `$http_user_agent`. For per-vhost analytics add **`$host`**:",
            "why_heading": "Why nginx-first?",
            "why_bullets": [
                "Predictable combined log format across fleets",
                "SSH tail of `/var/log/nginx/` without agent install on every box",
                "Apache is optional for mixed stacks or test nodes",
                "Security module still probes OS metrics independently of the web stack",
            ],
        },
    }


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _table(headers: tuple[str, str], rows: list[tuple[str, str]]) -> str:
    lines = [
        f"| {headers[0]} | {headers[1]} |",
        "|------|--------|",
    ]
    for a, b in rows:
        lines.append(f"| {a} | {b} |")
    return "\n".join(lines)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))


def _subsection(title: str, bullets: list[str], *, intro: str = "") -> str:
    body = f"\n{intro}\n\n" if intro else "\n"
    return f"### {title}{body}{_bullets(bullets)}\n"


def _shot(caption: str, filename: str) -> str:
    return f"![{caption}](screenshots/{filename})\n"


def _render_index(s: dict[str, Any]) -> str:
    links = _table((s["link_task"], s["link_where"]), s["links"])
    return f"""# {s["title"]}

{s["intro"]}

## {s["what_heading"]}

{s["what_body"]}

## {s["links_heading"]}

{links}

## {s["pages_heading"]}

{_table((s["link_task"], s["link_where"]), s["pages_rows"])}

> {s["docs_note"]}

## {s["shots_heading"]}

![{s["shot1"]}](screenshots/analytics-premium.png)

![{s["shot2"]}](screenshots/sidebar-nav.png)

> {s["shot_note"]}
"""


def _render_deployment(s: dict[str, Any]) -> str:
    reqs = "\n".join(f"- {r}" for r in s["reqs"])
    checklist = "\n".join(f"{i}. {item}" for i, item in enumerate(s["checklist"], 1))
    return f"""# {s["title"]}

## {s["req_heading"]}

{reqs}

## {s["install_heading"]}

{_INSTALL_SH}

{s["install_open"]}

## {s["docker_heading"]}

{_DOCKER_SH}

{s["docker_mount"]}

### {s["pg_heading"]}

{s["pg_body"]}

{_PG_SH}

{s["priority"]}

## {s["checklist_heading"]}

{checklist}

## {s["arch_heading"]}

{_Mermaid}

![{s["arch_caption"]}](screenshots/topbar-area.png)
"""


_SUBDOMAIN_NGINX = """```nginx
# /etc/nginx/nginx.conf — inside the http { } block
log_format skopos '$host $remote_addr - $remote_user [$time_local] '
                  '"$request" $status $body_bytes_sent "$http_referer" "$http_user_agent"';

access_log /var/log/nginx/access.log skopos;
```"""


def _render_configuration(s: dict[str, Any]) -> str:
    return f"""# {s["title"]}

## {s["servers_heading"]}

{s["servers_intro"]}

{_SERVERS_YAML}

{_table((s["field_col"], s["purpose_col"]), s["server_rows"])}

### {s["perm_heading"]}

{s["perm_body"]}

### {s["subdomain_heading"]}

{s["subdomain_body"]}

{_SUBDOMAIN_NGINX}

{s["subdomain_after"]}

## {s["agent_heading"]}

{s["agent_body"]}

## {s["env_heading"]}

{_table((s["field_col"], s["purpose_col"]), s["env_rows"])}

## {s["ui_heading"]}

{_table((s["field_col"], s["purpose_col"]), s["ui_rows"])}

## {s["settings_detail_heading"]}

{_table((s["field_col"], s["purpose_col"]), s["settings_detail_rows"])}

## {s["agent_detail_heading"]}

{s["agent_detail_body"]}

{_table(("Provider", "API key"), s["agent_detail_rows"])}

![{s["shot_caption"]}](screenshots/settings-fleet.png)

![Sidebar](screenshots/sidebar-nav.png)
"""


def _render_usage(s: dict[str, Any]) -> str:
    history_tabs = "\n".join(
        f"- **{name}** — {desc}" for name, desc in s["history_tabs"]
    )
    settings_sections = "\n".join(
        f"- **{name}** — {desc}" for name, desc in s["settings_sections"]
    )
    security_tabs = (
        _subsection(s["tab_score"], s["security_tab_score"])
        + _subsection(s["tab_report"], s["security_tab_report"])
        + _shot(s["security_tab_report_shot"], "security-summary-report.png")
        + _subsection(s["tab_security_overview"], s["security_tab_overview"])
        + _subsection(s["tab_ports"], s["security_tab_ports"])
        + _subsection(s["tab_knocks"], s["security_tab_knocks"])
        + _subsection(s["tab_resources"], s["security_tab_resources"])
        + _subsection(s["tab_audit"], s["security_tab_audit"])
        + _subsection(s["tab_3d"], s["security_tab_3d"])
        + _shot(s["security_tab_3d_shot"], "security-3d-map.png")
        + _subsection(s["tab_agent"], s["security_tab_agent"])
    )
    analytics_tabs = (
        _subsection(s["tab_overview"], s["analytics_tab_overview"])
        + _subsection(s["tab_geography"], s["analytics_tab_geography"])
        + _subsection(s["tab_audience"], s["analytics_tab_audience"])
        + _subsection(s["tab_content"], s["analytics_tab_content"])
        + _subsection(s["tab_sources"], s["analytics_tab_sources"])
        + _subsection(s["tab_journal"], s["analytics_tab_journal"])
        + _subsection(s["tab_system"], s["analytics_tab_system"])
    )
    return f"""# {s["title"]}

{s["intro"]}

## {s["daily_heading"]}

{_numbered(s["daily_steps"])}

## {s["shell_heading"]}

{s["shell_intro"]}

{_bullets(s["shell_bullets"])}

{_shot(s["shell_shot"], "sidebar-nav.png")}

## {s["quickstart_heading"]}

{s["quickstart_intro"]}

{_numbered(s["quickstart_steps"])}

> {s["quickstart_note"]}

{_shot(s["quickstart_shot"], "quick-start.png")}

## {s["analytics_heading"]}

{s["analytics_intro"]}

### {s["analytics_toolbar_heading"]}

{_bullets(s["analytics_toolbar_bullets"])}

### {s["analytics_briefing_heading"]}

{_bullets(s["analytics_briefing_bullets"])}

{_shot(s["analytics_briefing_shot"], "ai-briefing-card.png")}

### {s["analytics_tabs_heading"]}

{analytics_tabs}

{_shot(s["analytics_shot"], "analytics-premium.png")}

## {s["security_heading"]}

{s["security_intro"]}

{_bullets(s["security_sidebar_bullets"])}

{s["security_kpi_note"]}

### {s["security_tabs_heading"]}

{security_tabs}

## {s["history_heading"]}

{s["history_intro"]}

{_bullets(s["history_sidebar_bullets"])}

### {s["history_tabs_heading"]}

{history_tabs}

## {s["settings_heading"]}

{s["settings_intro"]}

{settings_sections}

{_shot(s["settings_shot"], "settings-fleet.png")}

## {s["agent_heading"]}

{s["agent_intro"]}

{_bullets(s["agent_bullets"])}

{_shot(s["agent_shot"], "floating-agent.png")}

## {s["ai_surfaces_heading"]}

{_table(("Surface", "Use when"), s["ai_surfaces_rows"])}

## {s["cli_heading"]}

{_CLI_SH}

## {s["topbar_heading"]}

{s["topbar_body"]}
"""


def _render_nginx(s: dict[str, Any]) -> str:
    not_sup = "\n".join(f"- {x}" for x in s["not_supported"])
    why = "\n".join(f"- {x}" for x in s["why_bullets"])
    return f"""# {s["title"]}

> {s["primary_note"]}

## {s["supported_heading"]}

{_table((s["source_col"], s["how_col"]), s["supported_rows"])}

## {s["not_supported_heading"]}

{not_sup}

{s["nginx_proxy_note"]}

## {s["apache_heading"]}

{s["apache_body"]}

{_APACHE_FORMAT}

{s["apache_metis"]}

### {s["admin_heading"]}

1. {s["admin_step_deploy"]}
2. {s["admin_step_traffic"]}
   {_CURL_SH}
3. {s["admin_step_config"]}
4. {s["admin_step_verify"]}

{s["admin_fixture"]}

## {s["rec_heading"]}

{s["rec_body"]}

{_NGINX_FORMAT}

## {s["why_heading"]}

{why}
"""


_RENDERERS = {
    "index": _render_index,
    "deployment": _render_deployment,
    "configuration": _render_configuration,
    "usage": _render_usage,
    "nginx": _render_nginx,
}


def render_all_guides(overlays: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    """Build markdown for every doc locale."""
    overlays = overlays or {}
    base = _base_strings()
    out: dict[str, dict[str, str]] = {}
    for lang in DOC_LANGS:
        merged = _deep_merge(base, overlays.get(lang, {}))
        out[lang] = {slug: fn(merged[slug]) for slug, fn in _RENDERERS.items()}
    return out
