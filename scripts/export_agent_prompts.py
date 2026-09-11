#!/usr/bin/env python3
"""One-time export: copy triple-quoted agent prompts from .py into agents/prompts/*.md"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "agents" / "prompts"

EXTRACTS = [
    ("agents/security.py", "SECURITY_SYSTEM_PROMPT", "security_system_prompt.md"),
    ("agents/devops.py", "DEVOPS_SYSTEM_PROMPT", "devops_system_prompt.md"),
    ("agents/marketing.py", "MARKETING_SYSTEM_PROMPT", "marketing_system_prompt.md"),
    ("agents/qa.py", "QA_SYSTEM_PROMPT", "qa_system_prompt.md"),
    ("agents/sales.py", "SALES_SYSTEM_PROMPT", "sales_system_prompt.md"),
    ("agents/design_critic.py", "DESIGN_CRITIC_SYSTEM", "design_critic_system_prompt.md"),
    ("agents/evolution_analyst.py", "EVOLUTION_SYSTEM_PROMPT", "evolution_analyst_system_prompt.md"),
    ("agents/methodologist.py", "_METHODOLOGIST_SYSTEM", "methodologist_system_prompt.md"),
    ("agents/dev.py", "DEV_CORE_PROMPT", "developer_core_prompt.md"),
    ("agents/analyst.py", "ANALYST_RESEARCH_PROMPT", "analyst_research_prompt.md"),
    ("agents/analyst.py", "ANALYST_MONITOR_PROMPT", "analyst_monitor_prompt.md"),
    ("agents/pm.py", "PM_SYSTEM_PROMPT_BASE", "pm_system_prompt_base.md"),
    ("agents/pm.py", "PM_SECTION_LANDING", "pm_section_landing.md"),
    ("agents/pm.py", "PM_SECTION_FULL", "pm_section_full.md"),
    ("agents/pm.py", "PM_OUTPUT_LANDING", "pm_output_landing.md"),
    ("agents/pm.py", "PM_OUTPUT_FULL", "pm_output_full.md"),
]


def extract_assign(text: str, name: str) -> str | None:
    m = re.search(rf"^{re.escape(name)}\s*=\s*\"\"\"([\s\S]*?)\"\"\"", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for src_rel, const, md_name in EXTRACTS:
        text = (ROOT / src_rel).read_text(encoding="utf-8")
        val = extract_assign(text, const)
        if not val:
            print(f"MISSING {src_rel}::{const}")
            continue
        (OUT / md_name).write_text(val + "\n", encoding="utf-8")
        print(f"wrote {md_name} ({len(val)} chars)")
        n += 1
    print(f"exported {n} prompts")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
