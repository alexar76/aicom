"""Check the raw HTML of two server cards in every supported language."""

import json
import sys
from collections import Counter
from html.parser import HTMLParser
from urllib.request import Request, urlopen

PUBLIC = "https://histor.modelmarket.dev"
CARDS = {
    "236eb5f0481cc99c": "com.aiapplyd/aiapplyd",
    "a792a696e5b056eb": "io.github.alexar76/warden",
}
LANGS = {
    "en": ("First observed", "Tool definitions as last observed", "signed observations"),
    "ru": ("Первое наблюдение", "Определения инструментов по последнему наблюдению", "Подписанные наблюдения"),
    "es": ("Primera observación", "Definiciones de herramientas en la última observación", "Observaciones firmadas"),
    "fr": ("Première observation", "Définitions d’outils lors de la dernière observation", "Observations signées"),
    "zh": ("首次观测", "最近观测到的工具定义", "签名观测"),
}


class CardHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lang = None
        self.canonical = []
        self.alternates = []
        self.meta = {}
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "html":
            self.lang = attr.get("lang")
        if tag == "title":
            self.in_title = True
        if tag == "link" and attr.get("rel") == "canonical":
            self.canonical.append(attr.get("href"))
        if tag == "link" and attr.get("rel") == "alternate" and "hreflang" in attr:
            self.alternates.append((attr["hreflang"], attr.get("href")))
        if tag == "meta":
            self.meta[attr.get("property") or attr.get("name")] = attr.get("content")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def check_html(html, base, name, lang):
    urls = {code: base if code == "en" else f"{base}?lang={code}" for code in LANGS}
    expected = urls[lang]
    parsed = CardHTML()
    parsed.feed(html)
    assert parsed.lang == lang, (expected, parsed.lang)
    assert parsed.canonical == [expected], (expected, parsed.canonical)
    assert Counter(parsed.alternates) == Counter({**urls, "x-default": base}.items()), expected
    assert parsed.meta["og:url"] == expected, expected
    assert parsed.title.endswith(" · HISTOR") and parsed.meta["og:title"] == parsed.title, expected
    fact, heading, description = LANGS[lang]
    assert description in parsed.meta["description"], expected
    assert parsed.meta["og:description"] == parsed.meta["description"], expected
    view = html.split('<div id="view" aria-live="polite">', 1)[1].split("</section>", 1)[0]
    assert name in view and fact in view and heading in view, expected
    return {
        "lang": lang, "title": parsed.title, "description": parsed.meta["description"],
        "canonical": expected, "og_url": parsed.meta["og:url"], "hreflang": dict(parsed.alternates),
        "html_card": {"server": name, "fact_label": fact, "tool_heading": heading},
    }


def live(base):
    report = []
    for target_id, name in CARDS.items():
        path = f"/s/{target_id}"
        for lang in LANGS:
            url = base + path + ("" if lang == "en" else f"?lang={lang}")
            request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AICOM SEO audit)"})
            with urlopen(request, timeout=12) as response:
                assert response.status == 200 and response.url == url, url
                assert response.headers.get_content_type() == "text/html", url
                assert "noindex" not in response.headers.get("X-Robots-Tag", "").lower(), url
                row = check_html(response.read().decode("utf-8"), PUBLIC + path, name, lang)
                report.append({"url": url, "http": response.status, **row})
    assert len({row["title"] for row in report}) == len(report)
    return report


if __name__ == "__main__":
    print(json.dumps(live(sys.argv[1] if len(sys.argv) == 2 else PUBLIC), ensure_ascii=False, indent=2))
