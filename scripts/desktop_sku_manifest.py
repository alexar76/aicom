"""Expected screenshot manifest for desktop Flutter SKUs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ActionKind = Literal[
    "landing",
    "nav_label",
    "nav_bottom",
    "nav_rail",
    "click_text",
    "interview_onboarding",
    "composer_export",
    "discovery_gap_detail",
    "discovery_sdk_export",
    "freelance_review_report",
    "wallet_popup",
]

DEV_WALLET_KEY = (
    "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
)


@dataclass(frozen=True)
class ScreenStep:
    name: str
    action: ActionKind = "landing"
    label: str = ""
    index: int = 0


@dataclass(frozen=True)
class SkuManifest:
    port: int
    wallet: bool = True
    bottom_nav_slots: int = 4
    dart_defines: dict[str, str] = field(default_factory=dict)
    screens: list[ScreenStep] = field(default_factory=list)


MANIFEST: dict[str, SkuManifest] = {
    "interview-prep-coach": SkuManifest(
        port=9922,
        wallet=False,
        dart_defines={"SKIP_ONBOARDING": "true"},
        screens=[
            ScreenStep("prep-dashboard", "landing"),
            ScreenStep("marketplace-browse", "nav_bottom", index=1),
            ScreenStep("mock-interview", "nav_bottom", index=0),
            ScreenStep("wallet-details", "wallet_popup"),
        ],
    ),
    "personal-finance-coach": SkuManifest(
        port=9923,
        screens=[
            ScreenStep("overview", "landing"),
            ScreenStep("import", "nav_rail", index=1),
            ScreenStep("marketplace", "nav_rail", index=2),
            ScreenStep("privacy", "nav_rail", index=3),
        ],
    ),
    "capability-composer": SkuManifest(
        port=9924,
        screens=[
            ScreenStep("canvas", "landing"),
            ScreenStep("discover", "nav_rail", index=1),
            ScreenStep("templates", "nav_rail", index=2),
            ScreenStep("export", "composer_export"),
        ],
    ),
    "cold-outreach-coach": SkuManifest(
        port=9925,
        bottom_nav_slots=5,
        screens=[
            ScreenStep("dashboard", "landing"),
            ScreenStep("composer", "nav_bottom", index=1),
            ScreenStep("deliverability", "nav_bottom", index=2),
            ScreenStep("marketplace", "nav_bottom", index=4),
        ],
    ),
    "creator-algorithm-coach": SkuManifest(
        port=9926,
        screens=[
            ScreenStep("dashboard", "landing"),
            ScreenStep("discover", "nav_rail", index=1),
            ScreenStep("publish", "nav_rail", index=2),
            ScreenStep("insights", "nav_rail", index=3),
        ],
    ),
    "discovery-prospector": SkuManifest(
        port=9927,
        screens=[
            ScreenStep("gaps-list", "landing"),
            ScreenStep("gap-detail", "discovery_gap_detail"),
            ScreenStep("telemetry", "click_text", "Refresh Telemetry"),
            ScreenStep("sdk-export", "discovery_sdk_export"),
        ],
    ),
    "freelance-contract-reviewer": SkuManifest(
        port=9928,
        screens=[
            ScreenStep("dashboard", "landing"),
            ScreenStep("upload", "nav_bottom", index=1),
            ScreenStep("marketplace", "nav_bottom", index=2),
            ScreenStep("review-report", "freelance_review_report"),
        ],
    ),
    "reputation-dashboard": SkuManifest(
        port=9929,
        screens=[
            ScreenStep("top-capabilities", "landing"),
            ScreenStep("my-reviews", "nav_bottom", index=1),
            ScreenStep("seller-console", "nav_bottom", index=2),
            ScreenStep("curator-console", "nav_bottom", index=3),
        ],
    ),
}


def expected_pngs(slug: str) -> list[str]:
    return [s.name + ".png" for s in MANIFEST[slug].screens]
