"""Deterministic editorial diagrams from one scene description, as SVG and PNG."""
import argparse
from hashlib import sha256
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONTS = Path("/System/Library/Fonts/Supplemental")
COLORS = {
    "paper": "#f8f6f1", "ink": "#272b36", "muted": "#626576",
    "line": "#d9d5ca", "violet": "#65518e", "green": "#247869",
    "red": "#ad514a", "white": "#ffffff", "wash": "#f0edf6",
}


class Scene:
    def __init__(self, width, height, title, description):
        self.width, self.height = width, height
        self.image = Image.new("RGB", (width, height), COLORS["paper"])
        self.draw = ImageDraw.Draw(self.image)
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                      f'viewBox="0 0 {width} {height}" role="img">',
                      f'<title>{html.escape(title)}</title><desc>{html.escape(description)}</desc>',
                      f'<rect width="100%" height="100%" fill="{COLORS["paper"]}"/>']

    def box(self, x, y, width, height, fill="white", stroke="line", radius=14):
        fill, stroke = COLORS.get(fill, fill), COLORS.get(stroke, stroke)
        self.draw.rounded_rectangle((x, y, x + width, y + height), radius=radius,
                                    fill=fill, outline=stroke, width=2)
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
                          f'rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')

    def text(self, x, y, text, size=28, color="ink", bold=False, mono=False):
        color = COLORS.get(color, color)
        face = "Andale Mono.ttf" if mono else "Arial Bold.ttf" if bold else "Arial.ttf"
        font = ImageFont.truetype(str(FONTS / face), size=size)
        self.draw.text((x, y), text, font=font, fill=color, anchor="lt")
        family = "'Andale Mono',monospace" if mono else "Arial,Helvetica,sans-serif"
        self.parts.append(f'<text x="{x}" y="{y + size * .84:.2f}" font-family="{family}" '
                          f'font-size="{size}" font-weight="{700 if bold else 400}" '
                          f'fill="{color}">{html.escape(text)}</text>')

    def line(self, x1, y1, x2, y2, color="line", width=2):
        color = COLORS.get(color, color)
        self.draw.line((x1, y1, x2, y2), fill=color, width=width)
        self.parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" '
                          f'stroke-width="{width}" fill="none"/>')

    def arrow(self, x, y1, y2, color):
        self.line(x, y1, x, y2, color=color, width=3)
        self.line(x, y2, x-9, y2-10, color=color, width=3)
        self.line(x, y2, x+9, y2-10, color=color, width=3)

    def save(self, destination, name):
        self.parts.append("</svg>")
        svg, png = destination / (name + ".svg"), destination / (name + ".png")
        svg.write_text("\n".join(self.parts) + "\n")
        self.image.save(png)
        return {"name": name, "width": self.width, "height": self.height,
                "svgSha256": sha256(svg.read_bytes()).hexdigest(),
                "pngSha256": sha256(png.read_bytes()).hexdigest()}


def advisory_flow(destination):
    scene = Scene(1100, 830, "An advisory signal lost its flag",
                  "Before and after projection of one informational advisory match. The repaired report "
                  "preserves advisory true and info severity, keeps the match in findings, and excludes it "
                  "from letter_points. The model still sees the report and humans review drafts.")
    scene.text(44, 35, "An advisory signal lost its flag", size=41, bold=True)
    scene.text(44, 96, "One informational match, reduced to the fields at issue", size=26, color="muted")
    columns = [(44, "BEFORE", "red"), (576, "AFTER", "green")]
    for x, label, accent in columns:
        scene.text(x, 152, label, size=27, bold=True, color=accent)
        for y in (198, 390, 582):
            scene.box(x, y, 480, 140, stroke=accent if y == 390 else "line")
        scene.text(x+23, 218, "Scanner result", size=29, bold=True)
        scene.text(x+23, 262, 'severity: "info"', size=27, mono=True)
        scene.text(x+23, 300, "advisory: true", size=27, mono=True)
        scene.arrow(x+240, 350, 376, accent)
        scene.text(x+23, 410, "Report finding", size=29, bold=True)
        scene.text(x+23, 454, 'severity: "low"' if label == "BEFORE" else 'severity: "info"',
                   size=27, mono=True)
        scene.text(x+23, 492, "advisory omitted" if label == "BEFORE" else "advisory: true",
                   size=27, mono=True, color=accent)
        scene.arrow(x+240, 542, 568, accent)
        scene.text(x+23, 602, "Draft input" if label == "BEFORE" else "Advice contract", size=29, bold=True)
        scene.text(x+23, 648, "all findings available" if label == "BEFORE" else "letter_points: []",
                   size=26, mono=label == "AFTER", color=accent)
        scene.text(x+23, 685, "no separate advice subset" if label == "BEFORE" else "match stays in full report",
                   size=25, color="muted")
    scene.text(44, 768, "The model still reads the full report; drafts need human review.", size=27, color="muted")
    return scene.save(destination, "reviewer-advisory-flow")


def eligible_sample(destination):
    scene = Scene(1000, 550, "Recorded findings eligible for a letter",
                  "Two saved November 6 checker examples: textokit has zero eligible letter points and "
                  "agent-exec has four. Local and container runs matched on the same downloaded documents. "
                  "These are eligibility counts for two examples, not measurements of draft quality or safety.")
    scene.text(44, 35, "Recorded findings eligible for a letter", size=39, bold=True)
    scene.text(44, 98, "Two examples from the November 6 comparison", size=27, color="muted")
    scene.text(44, 138, "Local and container checks used the same input documents", size=25, color="muted")
    x0, step, top, bottom = 310, 140, 226, 394
    for value in range(5):
        x = x0 + value*step
        scene.line(x, top-13, x, bottom+22)
        scene.text(x-7, top-54, str(value), size=25, color="muted")
    scene.text(44, 246, "textokit", size=34, bold=True)
    scene.text(44, 351, "agent-exec", size=34, bold=True)
    scene.box(x0-5, 254, 10, 10, fill="violet", stroke="violet", radius=5)
    scene.text(x0+19, 242, "0", size=34, bold=True, color="violet")
    scene.box(x0, 337, 4*step, 51, fill="violet", stroke="violet", radius=5)
    scene.text(x0+4*step+16, 346, "4", size=34, bold=True, color="violet")
    scene.text(44, 456, "Counts describe eligible findings in these two saved examples.", size=26)
    scene.text(44, 496, "Draft quality and seller safety were not measured here.", size=25, color="muted")
    return scene.save(destination, "reviewer-letter-points-sample")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    assets = [advisory_flow(args.out), eligible_sample(args.out)]
    manifest = {"renderer": "Deterministic Python scene to editable SVG and Pillow PNG",
                "fonts": "Arial and Andale Mono", "assets": assets,
                "sampleSource": "artifacts/supplier-review-letters-2026-11-06/ROLLOUT.md",
                "sampleDate": "2026-11-06", "sampleCounts": {"textokit": 0, "agent-exec": 4}}
    (args.out / "asset-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
