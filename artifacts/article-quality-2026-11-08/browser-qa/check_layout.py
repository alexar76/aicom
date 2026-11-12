"""Local-only browser QA of four technical articles, figures and revised covers."""
from hashlib import sha256
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
DIST = ROOT / "modelmarket-blog/dist"
FONTS = ROOT / "aimarket-hub/aimarket_hub/assets/fonts"
PLAN = json.loads((OUT.parent / "quality-plan.json").read_text())
report = {"mode": "All browser requests fulfilled from local dist and mirrored fonts; no external network",
          "pages": [], "svgTargets": [], "missingAssets": [], "pageErrors": [], "index": {}}


def target_for(url):
    parsed = urlparse(url)
    if parsed.netloc == "modelmarket.dev" and parsed.path.startswith("/blog/"):
        target = DIST / unquote(parsed.path.removeprefix("/blog/"))
        return target / "index.html" if target.is_dir() else target
    if parsed.netloc == "modelmarket.dev" and parsed.path.startswith("/assets/fonts/"):
        return FONTS / unquote(parsed.path.removeprefix("/assets/fonts/"))
    return None


def route_local(route):
    target = target_for(route.request.url)
    if target is None or not target.is_file():
        report["missingAssets"].append(route.request.url)
        route.fulfill(status=404, body="Local QA asset unavailable")
        return
    route.fulfill(status=200, body=target.read_bytes(),
                  content_type=mimetypes.guess_type(str(target))[0] or "application/octet-stream")


def images_ready(page):
    page.evaluate("""async () => {
      [...document.images].forEach(image => { image.loading = 'eager'; });
      await Promise.all([...document.images].map(image => image.decode().catch(() => {})));
      await document.fonts.ready;
    }""")


def metrics(page):
    return page.evaluate("""() => ({
      viewportWidth: innerWidth, documentWidth: document.documentElement.scrollWidth,
      documentHeight: document.documentElement.scrollHeight,
      title: document.querySelector('h1').innerText,
      cover: document.querySelector('.cover img').src,
      proseWidth: document.querySelector('.prose').getBoundingClientRect().width,
      figures: [...document.querySelectorAll('.prose img')].map(image => ({
        src:image.src, href:image.closest('a')?.href, loaded:image.complete && image.naturalWidth > 0,
        displayWidth:image.getBoundingClientRect().width, naturalWidth:image.naturalWidth})),
      code: [...document.querySelectorAll('.prose pre')].map(e => ({
        width:e.clientWidth, scrollWidth:e.scrollWidth, overflowX:getComputedStyle(e).overflowX})),
      tables: [...document.querySelectorAll('.prose .table')].map(e => ({
        width:e.clientWidth, scrollWidth:e.scrollWidth, overflowX:getComputedStyle(e).overflowX})),
      brokenImages: [...document.images].filter(e => !e.complete || !e.naturalWidth).map(e => e.src),
      fontsLoaded: document.fonts.check('700 30px Rajdhani') &&
        document.fonts.check('500 14px "JetBrains Mono"')
    })""")


OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for mode, viewport, theme in (("desktop", {"width":1440,"height":1100}, "dark"),
                                  ("mobile", {"width":390,"height":844}, "light")):
        context = browser.new_context(viewport=viewport, device_scale_factor=1,
                                      color_scheme=theme, reduced_motion="reduce")
        context.route("**/*", route_local)
        for item in PLAN:
            page = context.new_page()
            page.on("pageerror", lambda error: report["pageErrors"].append(str(error)))
            page.goto(item["blogUrl"], wait_until="networkidle")
            images_ready(page)
            prefix = item["pack"] + "-" + mode
            page.screenshot(path=str(OUT / (prefix + "-top.png")))
            page.screenshot(path=str(OUT / (prefix + "-full.png")), full_page=True)
            result = metrics(page)
            result.update(pack=item["pack"], mode=mode, theme=theme)
            result["documentOverflow"] = result["documentWidth"] > result["viewportWidth"] + 1
            assert result["cover"] == item["coverUrl"]
            assert sorted(figure["src"] for figure in result["figures"]) == sorted(item["figures"])
            assert sorted(figure["href"] for figure in result["figures"]) == sorted(item["figureSvgs"])
            assert all(figure["href"] == figure["src"].removesuffix(".png") + ".svg"
                       for figure in result["figures"])
            assert all(figure["loaded"] for figure in result["figures"])
            for href in item["figureSvgs"]:
                assert target_for(href).is_file(), href
                ET.parse(target_for(href))
            report["pages"].append(result)
            page.locator(".prose img").first.scroll_into_view_if_needed()
            page.screenshot(path=str(OUT / (prefix + "-figure.png")))
            if mode == "mobile":
                page.locator(".prose pre").first.scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / (prefix + "-code.png")))
                if page.locator(".prose .table").count():
                    page.locator(".prose .table").first.scroll_into_view_if_needed()
                    page.screenshot(path=str(OUT / (prefix + "-table.png")))
                # Exercise an actual image link to ensure its zoom target is an SVG document.
                first = page.locator(".prose img").first
                first.click()
                page.wait_for_url(result["figures"][0]["href"])
                assert page.evaluate("document.documentElement.tagName.toLowerCase()") == "svg"
                report["svgTargets"].append({"pack":item["pack"], "url":page.url,
                                             "actualImageClick":True, "svgDocument":True})
            page.close()
        context.close()

    context = browser.new_context(viewport={"width":1440,"height":1450}, device_scale_factor=1,
                                  color_scheme="dark", reduced_motion="reduce")
    context.route("**/*", route_local)
    page = context.new_page()
    page.goto("https://modelmarket.dev/blog/", wait_until="networkidle")
    images_ready(page)
    page.screenshot(path=str(OUT / "index-desktop-top.png"))
    index_images = page.locator("img").evaluate_all("images => images.map(image => image.src)")
    index_cards = []
    for item in PLAN:
        expected = [item["coverUrl"], item["blogUrl"] + "card-" + item["imageRevision"] + ".webp"]
        matched = [url for url in expected if url in index_images]
        assert matched, expected
        index_cards.append({"pack":item["pack"], "versionedImage":matched[0],
                            "coverSha256":sha256(target_for(item["coverUrl"]).read_bytes()).hexdigest()})
    report["index"] = {"cards":index_cards,
                       "fourDistinctCovers":len({card["coverSha256"] for card in index_cards}) == 4,
                       "documentWidth":page.evaluate("document.documentElement.scrollWidth"),
                       "viewportWidth":1440}
    page.close()
    context.close()
    browser.close()

report["uniqueInlineFiguresChecked"] = len({figure["src"] for result in report["pages"]
                                            for figure in result["figures"]})
assert report["uniqueInlineFiguresChecked"] == 8
assert not report["missingAssets"] and not report["pageErrors"]
assert all(not result["documentOverflow"] and not result["brokenImages"] for result in report["pages"])
(OUT / "qa.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"pages":len(report["pages"]), "inlineFigures":report["uniqueInlineFiguresChecked"],
                  "actualSvgImageClicks":len(report["svgTargets"]), "index":report["index"],
                  "missingAssets":report["missingAssets"], "pageErrors":report["pageErrors"]}, indent=2))
