"""Render publication figures from the saved synthetic billing experiment.

No experiment is executed here. Values are checked against three saved runs.
The canary arguments shown in figure 2 are an excerpt: recordId and
idempotencyKey are omitted for readability. Canary and default responses share
field names, not identical recordId values. Identical MCP messages belong to the
separate uncharged-matched-control experiment, not these two canary paths.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "kevin-fake-billing-2026-10-25/results/result.json"
OUT = Path("/private/tmp/devto-mcp-billing-2026-10-29/assets")
S = 2
W = 1280
IVORY = "#f5f0e6"
NAVY = "#162d3b"
TEAL = "#4b9c9a"
COPPER = "#d96c46"
MUTED = "#5a6b70"
RULE = "#dcded5"
WHITE = "#fffcf6"
TEAL_PALE = "#e5efea"
COPPER_PALE = "#f8e8dc"
FONTDIR = Path("/System/Library/Fonts/Supplemental")


def font(size, bold=False, mono=False):
    name = "Andale Mono.ttf" if mono else ("Arial Bold.ttf" if bold else "Arial.ttf")
    return ImageFont.truetype(str(FONTDIR / name), int(size * S))


class Canvas:
    def __init__(self, height):
        self.im = Image.new("RGB", (W * S, height * S), IVORY)
        self.d = ImageDraw.Draw(self.im)
        self.height = height
        self.bounds = []

    def text(self, xy, txt, size=26, fill=NAVY, bold=False, mono=False):
        x, y = xy
        f = font(size, bold=bold, mono=mono)
        box = self.d.textbbox((x * S, y * S), txt, font=f)
        assert box[0] >= 0 and box[2] <= W * S, (txt, box)
        assert box[1] >= 0 and box[3] <= self.height * S, (txt, box)
        self.bounds.append({"text": txt, "bounds": [v / S for v in box]})
        self.d.text((x * S, y * S), txt, font=f, fill=fill)

    def rect(self, box, fill, radius=16, outline=None, width=1):
        self.d.rounded_rectangle(tuple(int(v * S) for v in box), int(radius * S), fill,
                                 outline=outline, width=width * S)

    def line(self, points, fill=RULE, width=2):
        self.d.line([(int(x * S), int(y * S)) for x, y in points], fill=fill, width=width * S)

    def arrow(self, x1, y, x2, fill=NAVY):
        self.line([(x1, y), (x2 - 7, y)], fill, 3)
        self.d.polygon([(x2 * S, y * S), ((x2 - 10) * S, (y - 6) * S),
                        ((x2 - 10) * S, (y + 6) * S)], fill=fill)

    def dot(self, x, y, color, radius=7):
        self.d.ellipse(((x-radius)*S, (y-radius)*S, (x+radius)*S, (y+radius)*S), fill=color)

    def save(self, name, metadata):
        info = PngImagePlugin.PngInfo()
        info.add_text("Description", json.dumps(metadata, ensure_ascii=True, sort_keys=True))
        path = OUT / name
        self.im.resize((W, self.height), Image.Resampling.LANCZOS).save(path, pnginfo=info)
        return {"path": str(path), "size": [W, self.height], "textBounds": self.bounds,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "metadata": metadata}


def header(c, eyebrow, title, subtitle, title_size=48):
    c.rect((48, 36, 57, 65), TEAL, radius=3)
    c.text((72, 38), eyebrow, 22, fill=MUTED, bold=True)
    c.text((48, 85), title, title_size, bold=True)
    c.text((48, 151), subtitle, 26, fill=MUTED)


def footer(c, y):
    c.line([(48, y), (1232, y)])
    c.text((48, y + 18), "Synthetic fixture · 25 Oct 2026 · 3 repeats per case · No real money", 22, fill=MUTED)


def figure_paths():
    c = Canvas(816)
    header(c, "CONTROLLED EXPERIMENT / LOOKUP_RECORD", "One tool, two execution paths",
           "The probe exercised the free branch. The empty call reached a paid default.")
    for y, label, color, pale, arg_label, args, handler, note, credits in [
        (218, "HISTOR canary probe", TEAL, TEAL_PALE, "ARGUMENT EXCERPT", '{"mode":"preview"}', "preview", "Explicit free branch", "0"),
        (423, "Ordinary empty call", COPPER, COPPER_PALE, "COMPLETE ARGUMENTS", "{}", "purchase", "Handler default", "7"),
    ]:
        c.dot(57, y + 15, color, 6)
        c.text((75, y), label, 28, bold=True)
        top = y + 48
        c.rect((48, top, 440, top + 126), WHITE, outline=RULE)
        c.text((68, top + 17), arg_label, 20, fill=MUTED, bold=True)
        c.text((68, top + 59), args, 28, mono=True)
        c.arrow(452, top + 64, 480, color)
        c.rect((492, top, 806, top + 126), pale)
        c.text((514, top + 17), "HANDLER BRANCH", 20, fill=MUTED, bold=True)
        c.text((514, top + 49), handler, 33, bold=True)
        c.text((514, top + 91), note, 21, fill=MUTED)
        c.arrow(819, top + 64, 848, color)
        c.rect((861, top, 1232, top + 126), pale, outline=color, width=2)
        c.text((885, top + 16), "INDEPENDENT LEDGER", 20, fill=MUTED, bold=True)
        c.text((884, top + 44), credits, 59, fill=color, bold=True)
        c.text((944, top + 70), "mock credits", 28, bold=True)
    c.rect((48, 647, 1232, 728), NAVY)
    c.text((71, 660), "Both success responses: recordId + status", 29, WHITE, bold=True)
    c.text((71, 698), "Same field names; different recordId values. Neither reports the charge.", 23, "#dce8e3")
    footer(c, 754)
    return c, ["histor-current-canary", "empty-default-purchase"]


def timeline(c, y, label, outcome, detail, timeout=False):
    c.text((49, y), label, 26, bold=True)
    top = y + 49
    c.rect((48, top, 306, top + 112), WHITE, outline=RULE)
    c.text((68, top + 18), "TOOL CALL", 20, fill=MUTED, bold=True)
    c.text((68, top + 56), "arguments: {}", 26, mono=True)
    c.arrow(319, top + 56, 382, COPPER)
    c.rect((395, top, 720, top + 112), COPPER_PALE)
    c.text((417, top + 17), "BACKEND CHARGE", 20, fill=MUTED, bold=True)
    c.text((417, top + 54), "7 mock credits", 32, fill=COPPER, bold=True)
    c.arrow(733, top + 56, 796, COPPER)
    c.rect((809, top, 1232, top + 112), NAVY)
    c.text((832, top + 16), outcome, 29, WHITE, bold=not timeout, mono=not timeout)
    c.text((832, top + 62), detail, 24, "#dce8e3")


def figure_failure():
    c = Canvas(842)
    header(c, "CONTROLLED EXPERIMENT / FAILURE AND RETRY", "Charge first, failure later",
           "A tool error or timeout can follow a completed charge.", title_size=48)
    timeline(c, 250, "01  Tool reports an error", "isError: true", "Error returned after charge")
    timeline(c, 446, "02  Client receives no response", "No response", "Client times out after charge", timeout=True)
    c.rect((48, 660, 1232, 764), TEAL_PALE, outline=TEAL)
    c.text((70, 677), "RETRY WITH THE SAME OPERATION KEY", 21, fill=MUTED, bold=True)
    c.text((70, 713), "Two calls → 7 credits total", 30, fill=NAVY, bold=True)
    c.text((662, 681), "The backend must enforce", 25, fill=NAVY)
    c.text((662, 719), "duplicate suppression for the key.", 25, fill=NAVY)
    footer(c, 788)
    return c, ["charge-before-tool-error", "charge-before-timeout", "idempotent-purchase-retry"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = json.loads(SOURCE.read_text())
    expectations = {"histor-current-canary": 0, "empty-default-purchase": 7,
                    "charge-before-tool-error": 7, "charge-before-timeout": 7,
                    "idempotent-purchase-retry": 7}
    for case, credits in expectations.items():
        rows = [r for r in evidence["results"] if r["case"] == case]
        assert len(rows) == 3 and all(r["passed"] and r["mockCredits"] == credits for r in rows)
        if case == "idempotent-purchase-retry":
            assert all(r["charges"] == 1 for r in rows)
    metadata = {"source": str(SOURCE.relative_to(HERE.parents[2])),
                "sourceSha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                "scope": "Synthetic fixture; mock credits; not a prevalence estimate; no real money.",
                "sourceRecordedDate": "2026-10-25", "renderedDate": "2026-10-29"}
    results = []
    for name, draw in [("02-probe-vs-default.png", figure_paths),
                       ("03-charge-before-failure.png", figure_failure)]:
        c, cases = draw()
        results.append(c.save(name, {**metadata, "cases": cases}))
    (HERE / "diagrams-manifest.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps([{k:v for k,v in r.items() if k != "textBounds"} for r in results], indent=2))


if __name__ == "__main__":
    main()
