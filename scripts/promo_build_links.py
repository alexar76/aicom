#!/usr/bin/env python3
"""Generate UTM-tracked launch links from promo/utm/campaigns JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse, urlunparse


def build_url(base_url: str, path: str, params: dict[str, str]) -> str:
    root = base_url.rstrip("/")
    joined = urljoin(f"{root}/", path.lstrip("/"))
    parsed = urlparse(joined)
    query = urlencode({k: v for k, v in params.items() if v})
    return urlunparse(parsed._replace(query=query))


def main() -> int:
    ap = argparse.ArgumentParser(description="Build promo UTM links markdown table")
    ap.add_argument("--in", dest="input_path", default="promo/utm/campaigns.example.json")
    ap.add_argument("--out", dest="output_path", default="promo/utm/generated-links.md")
    args = ap.parse_args()

    src = Path(args.input_path)
    data = json.loads(src.read_text(encoding="utf-8"))
    base = str(data.get("base_url", "")).strip()
    links = data.get("links") or []
    if not base:
        raise SystemExit("base_url required in campaigns JSON")

    lines = [
        "# Generated UTM links",
        "",
        f"Source: `{src}` · base: `{base}`",
        "",
        "| Name | URL |",
        "|------|-----|",
    ]
    for item in links:
        name = str(item.get("name", ""))
        path = str(item.get("path", "/"))
        utm = {
            k: str(item[k])
            for k in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
            if item.get(k)
        }
        url = build_url(base, path, utm)
        lines.append(f"| `{name}` | {url} |")

    out = Path(args.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(links)} links)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
