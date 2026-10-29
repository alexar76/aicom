"""Render the maintained ecosystem guides on the ecosystem's own static host."""

import re
import shutil
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

WORKSPACE = Path(__file__).resolve().parents[2]
LOCALES = {"en": "EN", "ru": "RU", "es": "ES", "fr": "FR", "zh": "中文"}
LABELS = {
    "en": ("Knowledge base", "Whitepaper", "Markdown source", "Ecosystem"),
    "ru": ("База знаний", "Whitepaper", "Исходный Markdown", "Экосистема"),
    "es": ("Base de conocimiento", "Libro blanco", "Fuente Markdown", "Ecosistema"),
    "fr": ("Base de connaissances", "Livre blanc", "Source Markdown", "Écosystème"),
    "zh": ("知识库", "白皮书", "Markdown 源文件", "生态系统"),
}


def document_source(kind, locale):
    name = "knowledge-base" + ("" if locale == "en" else "-" + locale) + ".md"
    return WORKSPACE / "docs/ecosystem" / (name if kind == "knowledge" else "whitepaper/" + locale + ".md")


DOCUMENTS = {document_source(kind, locale).resolve(): (kind, locale)
             for kind in ("knowledge", "whitepaper") for locale in LOCALES}


def document_url(kind, locale):
    return "/" + document_source(kind, locale).relative_to(WORKSPACE).with_suffix(".html").as_posix()


def _slug(text):
    return re.sub(r"[^\w -]", "", text.lower().strip()).replace(" ", "-")


def build_documents(output, site_url, asset_prefix=""):
    # Build-time dependency only. Pages require no script or remote renderer.
    from markdown_it import MarkdownIt

    output = Path(output)
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    pages = {}
    headings = {}
    for source in DOCUMENTS:
        tokens = parser.parse(source.read_text())
        seen = {}
        ids = []
        for index, token in enumerate(tokens):
            if token.type != "heading_open":
                continue
            slug = _slug(tokens[index + 1].content)
            serial = seen.get(slug, 0)
            seen[slug] = serial + 1
            slug += "-" + str(serial) if serial else ""
            token.attrSet("id", slug)
            ids.append(slug)
        pages[source] = tokens
        headings[source] = ids

    def rewrite(url, source, image=False):
        parsed = urlsplit(url)
        target = None
        if parsed.scheme in ("http", "https") and parsed.netloc == "github.com":
            match = re.fullmatch(r"/alexar76/([^/]+)/blob/main/(.+)", parsed.path)
            if match:
                repo, path = match.groups()
                target = (WORKSPACE / path if repo == "aicom" else WORKSPACE / repo / path).resolve()
        elif not parsed.scheme and not parsed.netloc and parsed.path:
            target = (source.parent / unquote(parsed.path)).resolve()
        elif not parsed.scheme and not parsed.path and parsed.fragment:
            target = source
        if target in DOCUMENTS:
            kind, locale = DOCUMENTS[target]
            fragment = unquote(parsed.fragment)
            if fragment and fragment not in headings[target]:
                # Old Markdown navigation sometimes collapses punctuation differently.
                compact = lambda value: re.sub(r"-+", "-", value).strip("-")
                matches = [value for value in headings[target] if compact(value) == compact(fragment)]
                if len(matches) == 1:
                    fragment = matches[0]
            return document_url(kind, locale) + ("#" + fragment if fragment else "")
        if image and target and target.is_file() and target.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}:
            try:
                relative = target.relative_to(WORKSPACE)
            except ValueError:
                return url
            destination = output / "docs/assets" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, destination)
            return "/docs/assets/" + relative.as_posix()
        if target and not parsed.scheme:
            try:
                relative = target.relative_to(WORKSPACE)
            except ValueError:
                return url
            return urlunsplit(("https", "github.com", "/alexar76/aicom/blob/main/" + relative.as_posix(), parsed.query, parsed.fragment))
        return url

    for source, (kind, locale) in DOCUMENTS.items():
        tokens = pages[source]
        for token in tokens:
            for child in token.children or []:
                if child.type == "link_open":
                    child.attrSet("href", rewrite(child.attrGet("href") or "", source))
                elif child.type == "image":
                    child.attrSet("src", rewrite(child.attrGet("src") or "", source, image=True))
        labels = LABELS[locale]
        title = next(token.content for token in tokens if token.type == "inline")
        canonical = site_url.rstrip("/") + document_url(kind, locale)
        languages = "".join(f'<a href="{document_url(kind, lang)}" lang="{lang}" hreflang="{lang}"' + (' aria-current="page"' if lang == locale else '') + f'>{name}</a>' for lang, name in LOCALES.items())
        source_url = document_url(kind, locale).replace(".html", ".md")
        html = f'''<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} — AICOM Ecosystem</title><link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="{asset_prefix}/fonts/fonts.css"><link rel="stylesheet" href="/docs/document.css"></head>
<body><header><a class="brand" href="{'/' if locale == 'en' else '/' + locale + '/'}">AICOM ECOSYSTEM</a>
<nav aria-label="Documents"><a href="{document_url('knowledge', locale)}">{labels[0]}</a><a href="{document_url('whitepaper', locale)}">{labels[1]}</a></nav>
<nav class="languages" aria-label="Language">{languages}</nav></header>
<main><article>{parser.renderer.render(tokens, parser.options, {})}</article></main>
<footer><a href="{source_url}" download>{labels[2]}</a><a href="{'/' if locale == 'en' else '/' + locale + '/'}">{labels[3]}</a></footer></body></html>'''
        destination = output / document_url(kind, locale).lstrip("/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html)
        destination.with_suffix(".md").write_text(source.read_text())
    css_target = output / "docs/document.css"
    css_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).with_name("document.css"), css_target)
    return [document_url(kind, locale) for kind, locale in DOCUMENTS.values()]
