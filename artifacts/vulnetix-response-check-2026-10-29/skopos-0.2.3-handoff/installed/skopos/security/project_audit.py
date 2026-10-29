from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from ..config import AppConfig
from ..db_dialect import is_postgres_url, resolve_db_target
from ..password_policy import validate_dashboard_password


@dataclass(frozen=True)
class ProjectSecurityIssue:
    severity: str  # critical | high | medium | low | info
    category: str
    title: str
    detail: str
    recommendation: str


def audit_stats_project(cfg: AppConfig, *, agent_yaml_path: str = "./agent.yaml") -> list[ProjectSecurityIssue]:
    """Audit security posture of the SKOPOS application itself."""
    issues: list[ProjectSecurityIssue] = []

    # ── Dashboard access control ─────────────────────────────────────────
    dash_pwd = os.environ.get("SKOPOS_DASHBOARD_PASSWORD", "").strip()
    if not dash_pwd:
        issues.append(
            ProjectSecurityIssue(
                severity="high",
                category="project",
                title="Dashboard has no authentication",
                detail="SKOPOS_DASHBOARD_PASSWORD is not set — anyone with network access can view traffic and security data.",
                recommendation="Set SKOPOS_DASHBOARD_PASSWORD in .env / docker-compose before exposing port 8501.",
            )
        )
    else:
        ok, failed = validate_dashboard_password(dash_pwd)
        if not ok:
            issues.append(
                ProjectSecurityIssue(
                    severity="medium",
                    category="project",
                    title="Dashboard password does not meet policy",
                    detail=f"Current SKOPOS_DASHBOARD_PASSWORD fails: {', '.join(failed)}.",
                    recommendation="Settings → Dashboard access → set a stronger password (min length, letter + digit, not common).",
                )
            )

    # ── API keys exposure ──────────────────────────────────────────────────
    for env_name in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        if os.environ.get(env_name):
            if not dash_pwd:
                issues.append(
                    ProjectSecurityIssue(
                        severity="medium",
                        category="project",
                        title=f"{env_name} loaded without dashboard auth",
                        detail="LLM API keys are in process environment; unauthenticated dashboard increases blast radius.",
                        recommendation="Enable SKOPOS_DASHBOARD_PASSWORD and restrict network access to SKOPOS.",
                    )
                )
            break

    agent_path = Path(agent_yaml_path).expanduser()
    if agent_path.exists():
        text = agent_path.read_text(encoding="utf-8")
        if "api_key:" in text.lower() and "api_key_env" not in text:
            if "sk-" in text or "api_key: " in text:
                issues.append(
                    ProjectSecurityIssue(
                        severity="critical",
                        category="project",
                        title="Plaintext API key in agent.yaml",
                        detail="agent.yaml may contain a hardcoded API key instead of api_key_env reference.",
                        recommendation="Use api_key_env only; never commit secrets. Rotate any exposed key.",
                    )
                )

    # ── SQLite database permissions ────────────────────────────────────────
    db_target = resolve_db_target(cfg)
    if not is_postgres_url(db_target):
        db = Path(db_target).expanduser()
        if db.exists():
            mode = stat.S_IMODE(db.stat().st_mode)
            if mode & stat.S_IROTH:
                issues.append(
                    ProjectSecurityIssue(
                        severity="medium",
                        category="project",
                        title="Database world-readable",
                        detail=f"{db} mode {oct(mode)} — other local users can read HTTP logs and security events.",
                        recommendation="chmod 600 skopos.sqlite3",
                    )
                )

    # ── Config file permissions ────────────────────────────────────────────
    for rel in ("servers.yaml", "agent.yaml"):
        p = Path(rel).expanduser()
        if p.exists():
            mode = stat.S_IMODE(p.stat().st_mode)
            if mode & (stat.S_IROTH | stat.S_IWOTH):
                issues.append(
                    ProjectSecurityIssue(
                        severity="low",
                        category="project",
                        title=f"{rel} readable by others",
                        detail=f"File mode {oct(mode)} exposes server topology.",
                        recommendation=f"chmod 600 {rel}",
                    )
                )

    # ── SSH MITM risk ────────────────────────────────────────────────────
    strict = os.environ.get("SKOPOS_SSH_STRICT_HOST_KEYS", "").lower() in ("1", "true", "yes")
    if not strict:
        issues.append(
            ProjectSecurityIssue(
                severity="medium",
                category="project",
                title="SSH host keys not verified (MITM risk)",
                detail="SKOPOS_SSH_STRICT_HOST_KEYS is off — AutoAddPolicy accepts unknown server fingerprints.",
                recommendation="Set SKOPOS_SSH_STRICT_HOST_KEYS=1 and populate ~/.ssh/known_hosts for all servers.",
            )
        )

    # ── Streamlit network exposure ─────────────────────────────────────────
    addr = os.environ.get("STREAMLIT_SERVER_ADDRESS", "localhost")
    if addr in ("0.0.0.0", "::") and not dash_pwd:
        issues.append(
            ProjectSecurityIssue(
                severity="critical",
                category="project",
                title="SKOPOS bound to all interfaces without auth",
                detail="Dashboard listens on 0.0.0.0 with no password — full analytics + security data exposed.",
                recommendation="Use reverse proxy with TLS + auth, or SKOPOS_DASHBOARD_PASSWORD + firewall allowlist.",
            )
        )

    # ── SSH key passphrase in env ──────────────────────────────────────────
    if os.environ.get("SKOPOS_SSH_KEY_PASSPHRASE") and not dash_pwd:
        issues.append(
            ProjectSecurityIssue(
                severity="low",
                category="project",
                title="SSH passphrase in environment",
                detail="SKOPOS_SSH_KEY_PASSPHRASE is set; combined with open dashboard this widens credential exposure.",
                recommendation="Run SKOPOS on a hardened host; lock down dashboard access.",
            )
        )

    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    issues.sort(key=lambda x: sev_order.get(x.severity, 9))
    return issues
