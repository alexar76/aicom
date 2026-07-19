#!/usr/bin/env python3
"""Split AdminTabs.tsx into web/frontend/components/admin/tabs/*.tsx and replace with barrel."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web/frontend/components/admin/AdminTabs.tsx"
OUT_DIR = ROOT / "web/frontend/components/admin/tabs"
# Shared header: 'use client' + imports through line 85 (inclusive, 1-based)
HEADER_END = 85


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    header = "".join(lines[:HEADER_END])

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # pipelineConstants.ts — lines 500–529
    const_src = "".join(lines[499:529]).replace("const ", "export const ")
    (OUT_DIR / "pipelineConstants.ts").write_text(const_src, encoding="utf-8")

    def w(name: str, lo: int, hi: int, extra: str = "") -> None:
        """Copy 1-based inclusive line range [lo, hi]."""
        chunk = "".join(lines[lo - 1 : hi])
        (OUT_DIR / name).write_text(f"{header}\n{extra}{chunk}", encoding="utf-8")

    w("HumanReviewGatePanel.tsx", 532, 628)
    w("StorefrontFollowupPanel.tsx", 631, 1165)

    w(
        "PipelineTab.tsx",
        1167,
        2242,
        "import { CATEGORY_LABELS, CATEGORY_COLORS, STAGE_AGENT_TITLE } from './pipelineConstants';\n"
        "import { HumanReviewGatePanel } from './HumanReviewGatePanel';\n"
        "import { StorefrontFollowupPanel } from './StorefrontFollowupPanel';\n\n",
    )

    w("DashboardTab.tsx", 87, 317)
    w("NewProductTab.tsx", 321, 496)

    w("AgentsTab.tsx", 2246, 2308)
    w("FilesTab.tsx", 2312, 2580)

    w("ProviderFormModal.tsx", 2584, 2793)
    w("RoutingRulesEditor.tsx", 2794, 2933)

    w(
        "ProvidersTab.tsx",
        2934,
        3254,
        "import { ProviderFormModal } from './ProviderFormModal';\n"
        "import { RoutingRulesEditor } from './RoutingRulesEditor';\n\n",
    )

    w("SecurityTab.tsx", 3258, 3521)

    w("LLMLogsTab.tsx", 3523, 3771)

    w("AgentLogsTab.tsx", 3775, 3945)

    w("SandboxTab.tsx", 3949, 4307)

    w("DemoReplayMonitorSection.tsx", 4311, 4473)

    w(
        "MonitorTab.tsx",
        4477,
        5064,
        "import { DemoReplayMonitorSection } from './DemoReplayMonitorSection';\n\n",
    )

    w("DirectorTab.tsx", 5068, 5804)

    w("DiscoveryTab.tsx", 5806, 5935)

    w("SettingsTab.tsx", 5939, 6854)

    w("CorporateChatTab.tsx", 6858, 7111)

    barrel = """'use client';

export { DashboardTab } from './tabs/DashboardTab';
export { NewProductTab } from './tabs/NewProductTab';
export { HumanReviewGatePanel } from './tabs/HumanReviewGatePanel';
export { StorefrontFollowupPanel } from './tabs/StorefrontFollowupPanel';
export { PipelineTab } from './tabs/PipelineTab';
export { AgentsTab } from './tabs/AgentsTab';
export { ProviderFormModal } from './tabs/ProviderFormModal';
export { RoutingRulesEditor } from './tabs/RoutingRulesEditor';
export { ProvidersTab } from './tabs/ProvidersTab';
export { SecurityTab } from './tabs/SecurityTab';
export { LLMLogsTab } from './tabs/LLMLogsTab';
export { AgentLogsTab } from './tabs/AgentLogsTab';
export { SandboxTab } from './tabs/SandboxTab';
export { DemoReplayMonitorSection } from './tabs/DemoReplayMonitorSection';
export { MonitorTab } from './tabs/MonitorTab';
export { DirectorTab } from './tabs/DirectorTab';
export { DiscoveryTab } from './tabs/DiscoveryTab';
export { SettingsTab } from './tabs/SettingsTab';
export { CorporateChatTab } from './tabs/CorporateChatTab';
"""
    SRC.write_text(barrel, encoding="utf-8")
    print("OK — wrote", OUT_DIR, "and barrel", SRC.relative_to(ROOT))


if __name__ == "__main__":
    main()
