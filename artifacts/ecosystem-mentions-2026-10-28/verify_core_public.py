"""Read-only verification of public external mention pages; no credentials or paid calls."""
import concurrent.futures
import datetime
import hashlib
import html.parser
import json
import pathlib
import re
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
URLS = [
    "https://agenteconomy.report/s/modelmarket.dev.json",
    "https://agenteconomy.report/s/modelmarket.dev",
    "https://x402-list.com/api/v1/services/aimarket/volume",
    "https://x402-list.com/api/v1/services/aimarket/buyers",
    "https://www.x402-list.com/services/aimarket",
    "https://mcp.market/server/modelmarket-weather",
    "https://inite.ai/en/atlas/modelmarket.dev",
    "https://inite.ai/en/atlas/modelmarket.dev/alternatives",
    "https://inite.ai/en/atlas/all/m",
    "https://inite.ai/en/atlas/method",
    "https://mcpbridge.org/directory/ai-ml/",
]


class TextParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
        self.in_title = False
        self.title = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def fetch(url):
    row = {"requested_url": url, "retrieved_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (public-source-verification)"})
        with urllib.request.urlopen(req, timeout=40) as response:
            body = response.read(4_000_000)
            row.update(status=response.status, final_url=response.url,
                       content_type=response.headers.get("Content-Type"), bytes=len(body),
                       sha256=hashlib.sha256(body).hexdigest())
        decoded = body.decode("utf-8", errors="replace")
        if "json" in row["content_type"] or url.endswith(".json") or "/api/" in url:
            try:
                row["public_json"] = json.loads(decoded)
            except ValueError:
                row["parse_error"] = "Not valid JSON"
        else:
            parser = TextParser()
            parser.feed(decoded)
            text = " ".join(parser.parts)
            row["title"] = " ".join(parser.title)
            # Short factual contexts only; full foreign pages are not saved.
            patterns = [r"modelmarket", r"GAIA", r"scan report", r"scanner v", r"No reviews", r"91/100",
                        r"11/11", r"2026-10-2[678]", r"Updated", r"read again", r"58", r"aimarket-plugins"]
            snippets = []
            for pattern in patterns:
                for match in list(re.finditer(pattern, text, re.I))[:2]:
                    start, end = max(0, match.start() - 70), min(len(text), match.end() + 140)
                    snippets.append(text[start:end])
            row["factual_contexts"] = list(dict.fromkeys(snippets))[:16]
            row["has_modelmarket_domain"] = "modelmarket.dev" in text
            row["has_alexar76"] = "alexar76" in text
    except urllib.error.HTTPError as exc:
        row.update(status=exc.code, error=str(exc))
    except Exception as exc:
        row["error"] = type(exc).__name__ + ": " + str(exc)
    return row


def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(fetch, URLS))
    output = ROOT / "core-public-verification.json"
    output.write_text(json.dumps({"checked_date_moscow": "2026-10-28", "method": "Public unauthenticated HTTP GET only", "sources": rows}, ensure_ascii=False, indent=2) + "\n")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
