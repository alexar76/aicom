"""Render local SVGs using Chromium; no external requests are permitted."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
directory = parser.parse_args().directory.resolve()
results = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=1)
    page.route("**/*", lambda route: route.abort() if route.request.url.startswith(("http:", "https:")) else route.continue_())
    for source in sorted(directory.glob("*.svg")):
        page.goto(source.as_uri())
        svg = page.locator("svg")
        svg.screenshot(path=str(source.with_suffix(".png")))
        results.append({"source": source.name, "output": source.with_suffix(".png").name,
                        "bounds": svg.bounding_box()})
    browser.close()
print(json.dumps(results, indent=2))
