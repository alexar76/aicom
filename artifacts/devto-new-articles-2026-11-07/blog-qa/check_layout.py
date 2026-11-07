"""Render only local built files; every browser request is intercepted locally."""
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
DIST = ROOT / "modelmarket-blog/dist"
FONTS = ROOT / "aimarket-hub/aimarket_hub/assets/fonts"
OUT = Path(__file__).resolve().parent
PLAN = json.loads((OUT.parent / "editorial-blog-plan.json").read_text())
report = {
    "mode": "Local built files fulfilled through Playwright routes; no external requests allowed",
    "desktop": [], "mobile": [], "missingAssets": [], "pageErrors": [],
}


def local_route(route):
    url = urlparse(route.request.url)
    if url.netloc == "modelmarket.dev" and url.path.startswith("/blog/"):
        target = DIST / unquote(url.path.removeprefix("/blog/"))
        if target.is_dir():
            target = target / "index.html"
    elif url.netloc == "modelmarket.dev" and url.path.startswith("/assets/fonts/"):
        target = FONTS / unquote(url.path.removeprefix("/assets/fonts/"))
    else:
        report["missingAssets"].append({"url": route.request.url, "reason": "No local mapping"})
        route.abort()
        return
    if not target.is_file():
        report["missingAssets"].append({"url": route.request.url, "reason": "Local file missing"})
        route.fulfill(status=404, body="Local QA asset not found")
        return
    route.fulfill(status=200, body=target.read_bytes(),
                  content_type=mimetypes.guess_type(str(target))[0] or "application/octet-stream")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    modes = [
        ("desktop", {"width": 1440, "height": 1100}, "dark", PLAN),
        ("mobile", {"width": 390, "height": 844}, "light",
         [item for item in PLAN if item["pack"].startswith(("ard-", "histor-"))]),
    ]
    for mode, viewport, scheme, items in modes:
        context = browser.new_context(viewport=viewport, device_scale_factor=1,
                                      color_scheme=scheme, reduced_motion="reduce")
        context.route("**/*", local_route)
        for item in items:
            page = context.new_page()
            page.on("pageerror", lambda error: report["pageErrors"].append(str(error)))
            page.goto(item["blogUrl"], wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            # Full-page screenshots do not trigger below-fold lazy images. Load
            # those local images before checking them for actual failures.
            page.evaluate("""async () => {
              [...document.images].forEach(image => { image.loading = 'eager'; });
              await Promise.all([...document.images].map(image => image.decode().catch(() => {})));
            }""")
            page.screenshot(path=str(OUT / (item["pack"] + "-" + mode + "-top.png")))
            page.screenshot(path=str(OUT / (item["pack"] + "-" + mode + "-full.png")), full_page=True)
            metrics = page.evaluate("""() => ({
              viewportWidth: innerWidth,
              documentWidth: document.documentElement.scrollWidth,
              documentHeight: document.documentElement.scrollHeight,
              title: document.querySelector('h1').innerText,
              titleWidth: document.querySelector('h1').getBoundingClientRect().width,
              bodyFont: getComputedStyle(document.querySelector('.prose')).fontSize,
              proseWidth: document.querySelector('.prose').getBoundingClientRect().width,
              codeBlocks: [...document.querySelectorAll('.prose pre')].map(e => ({
                width:e.clientWidth, scrollWidth:e.scrollWidth, overflowX:getComputedStyle(e).overflowX})),
              tables: [...document.querySelectorAll('.prose .table')].map(e => ({
                width:e.clientWidth, scrollWidth:e.scrollWidth, overflowX:getComputedStyle(e).overflowX})),
              brokenImages: [...document.images].filter(e => !e.complete || !e.naturalWidth).map(e => e.src),
              fontsLoaded: document.fonts.check('700 30px Rajdhani') &&
                document.fonts.check('500 14px "JetBrains Mono"')
            })""")
            metrics.update(pack=item["pack"], theme=scheme)
            metrics["documentOverflow"] = metrics["documentWidth"] > metrics["viewportWidth"] + 1
            report[mode].append(metrics)
            if mode == "mobile":
                focus = (page.locator(".prose .table").first if item["pack"].startswith("histor-")
                         else page.locator(".prose pre").nth(1))
                focus.scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / (item["pack"] + "-" + mode + "-detail.png")))
            page.close()
        context.close()
    browser.close()

(OUT / "qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
