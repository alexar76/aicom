# -*- coding: utf-8 -*-
"""Rebuild a local, non-network inventory and a bounded recheck queue."""
import collections
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASES = [
    ROOT / "artifacts/external-links-2026-11-10",
    ROOT / "artifacts/external-signals-2026-11-09",
    ROOT / "artifacts/external-social-regional-2026-11-09",
    ROOT / "artifacts/external-social-regional-deeper-2026-11-09",
]
REPORTS = [
    "artifacts/external-links-2026-11-10/report.ru.md",
    "artifacts/external-signals-2026-11-09/report.ru.md",
    "artifacts/external-social-regional-2026-11-09/report.ru.md",
    "artifacts/external-social-regional-deeper-2026-11-09/report.ru.md",
]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            if d.get("href"):
                self.links.append(d["href"])


def own_url(url):
    try:
        p = urlsplit(html.unescape(url))
    except ValueError:
        return False
    h = (p.hostname or "").lower()
    return (h == "modelmarket.dev" or h.endswith(".modelmarket.dev")
            or h in {"magic-ai-factory.com", "attestedmemory.net", "hub.attestedmemory.net",
                     "alexar76.github.io", "pingblip.com", "world.pingblip.com", "forge.pingblip.com",
                     "emberlinedesk.com", "independentai.network"}
            or (h in {"github.com", "raw.githubusercontent.com", "huggingface.co", "dev.to"}
                and p.path.startswith("/alexar76/"))
            or (h in {"doi.org", "zenodo.org"} and any(x in url for x in ["23512760", "23512761"])))


mapping = yaml.safe_load((ROOT / "scripts/satellite-map.yaml").read_text())
map_lines = (ROOT / "scripts/satellite-map.yaml").read_text().splitlines()
components = []
domains = collections.defaultdict(list)
for s in mapping["satellites"]:
    line = next(i for i, t in enumerate(map_lines, 1) if t.strip() == "- id: " + s["id"])
    row = {"id": s["id"], "repo": s.get("repo"), "paths": s.get("paths", []),
           "homepage": s.get("homepage"), "github_published_declared": s.get("github_published", True),
           "publication_field_explicit": "github_published" in s,
           "role": "profile" if s["id"] == "profile" else ("wiki" if s.get("repo", "").endswith(".wiki") else "component_or_collection"),
           "provenance": {"file": "scripts/satellite-map.yaml", "line": line}}
    if row["github_published_declared"]:
        row["repository_target"] = "https://github.com/alexar76/" + s["repo"]
    row["description"] = s.get("description", "")
    components.append(row)
    if row["homepage"] and own_url(row["homepage"]):
        domains[urlsplit(row["homepage"]).hostname].append(row["provenance"])

maintained = ["scripts/github-io/index.html", "ecosystem-landing/index.html",
              "pingblip/README.md", "pantheon/README.md"]
entry_targets = []
for f in maintained:
    for n, line in enumerate((ROOT / f).read_text().splitlines(), 1):
        for u in re.findall(r'https?://[^\s<>"\x27)]+', line):
            u = html.unescape(u).rstrip(".,;`")
            if own_url(u):
                ref = {"file": f, "line": n}
                domains[urlsplit(u).hostname].append(ref)
                entry_targets.append({"url": u, "provenance": ref})

shared_hosts = {"github.com", "raw.githubusercontent.com"}
inventory = {
    "date_client": "2026-11-10", "network_requests": 0,
    "identity": "alexar76", "mapping_is_local_declaration_not_live_remote_verification": True,
    "counts": {"mapping_entries": len(components),
               "github_published_declared_entries": sum(x["github_published_declared"] for x in components),
               "github_unpublished_declared_entries": sum(not x["github_published_declared"] for x in components),
               "published_component_or_collection_entries_excluding_profile_and_wikis": sum(x["github_published_declared"] and x["role"] == "component_or_collection" for x in components),
               "profile_entries": sum(x["role"] == "profile" for x in components),
               "wiki_entries": sum(x["role"] == "wiki" for x in components),
               "own_public_hosts_in_selected_maintained_sources": len(set(domains) - shared_hosts),
               "shared_hosting_origins_with_identity_scoped_targets": len(set(domains) & shared_hosts)},
    "components": components,
    "own_public_hosts": [{"host": h, "provenance": list({(v["file"], v["line"]): v for v in refs}.values())}
                         for h, refs in sorted(domains.items()) if h not in shared_hosts],
    "shared_hosting_origins": [{"host": h, "identity_scope": "/alexar76/", "provenance": refs}
                               for h, refs in sorted(domains.items()) if h in shared_hosts],
    "maintained_entry_targets": list({x["url"]: x for x in entry_targets}.values()),
    "supplementary_nonmapped_surfaces": [
        {"name": "PANTHEON / The Human Trace", "url": "https://trace.modelmarket.dev/", "source": "pantheon/README.md:230"},
        {"name": "PingBlip game, world and forge", "urls": ["https://pingblip.com", "https://world.pingblip.com", "https://forge.pingblip.com"], "source": "pingblip/README.md:18"},
        {"name": "Independent AI products", "url": "https://independentai.network", "source": "docs/growth/external-mentions-2026-10-26.ru.md:128", "note": "Historical audit identity marker; not separately counted as a satellite/component."}],
    "limits": ["60 mapping entries are not 60 independent products or operators; profile, wikis, historical aliases and collections are present.",
               "github_published defaults to true in the local map; this script does not assert remote existence.",
               "Hosts come from selected maintained entry sources, not a full domain/DNS inventory.",
               "A local declaration or first-party crosslink is not an external endorsement."]}
(OUT / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")

# Preserve the indexes' original file/UTC/hash metadata rather than refetching old evidence.
captures = []
for base in BASES:
    for p in base.rglob("*index.json"):
        if any(x in p.relative_to(base).parts for x in {"baseline", "ecosystem", "technical", "recheck"}):
            continue
        try:
            data = json.loads(p.read_text())
        except (ValueError, UnicodeError):
            continue
        rows = data if isinstance(data, list) else []
        for row in rows:
            if isinstance(row, dict) and row.get("url") and row.get("file"):
                body = p.parent / row["file"]
                if not body.exists():
                    body = ROOT / row["file"]
                if body.exists():
                    captures.append((p, row, body))


def source_normalized(u):
    u = u.split("#")[0].rstrip("/")
    u = u.replace("https://raw.githubusercontent.com/", "https://github.com/")
    u = u.replace("/blob/", "/")
    return u


def collect(source):
    matched = []
    refs = []
    for p, row, body in captures:
        try:
            raw = body.read_text()
        except UnicodeError:
            continue
        exact = source_normalized(row["url"]) == source_normalized(source)
        if source == "https://github.com/Paraphern/rugsnare" and row["url"] == "https://raw.githubusercontent.com/Paraphern/rugsnare/main/README.md":
            exact = True
        selected = None
        if "github.com/" in source and "#issuecomment-" in source and raw[:1] in "[{":
            try:
                obj = json.loads(raw)
                opts = obj if isinstance(obj, list) else [obj]
                selected = next((o for o in opts if isinstance(o, dict) and o.get("html_url") == source), None)
            except ValueError:
                pass
        if not exact and selected is None:
            continue
        text = selected.get("body", "") if selected else raw
        parser = Links()
        parser.feed(text)
        hrefs = {urljoin(row.get("final_url", row["url"]), h) for h in parser.links}
        urls = set(re.findall(r'https?://[^\s<>"\x27)]+', text))
        refs += [{"url": html.unescape(u).rstrip(".,;`\\"), "form": "html_href"} for u in sorted(hrefs) if own_url(u)]
        refs += [{"url": html.unescape(u).rstrip(".,;`\\"), "form": "text_or_markdown_url"} for u in sorted(urls) if own_url(u) and u not in hrefs]
        matched.append({"index": str(p.relative_to(ROOT)), "body": str(body.relative_to(ROOT)),
                        "captured_at_utc": row.get("observed_at_utc", row.get("retrieved_at_utc", row.get("checked_at_utc"))),
                        "status": row.get("status"), "sha256": row.get("sha256"),
                        "body_hash_valid": hashlib.sha256(body.read_bytes()).hexdigest() == row.get("sha256"),
                        "selected_comment_only": selected is not None,
                        "capture_url": row["url"]})
    return matched, list({(x["url"], x["form"]): x for x in refs}.values())


# Curated sources, not a claim of new discovery. Distinct comments can share one operator.
CANDIDATES = [
 ("CrawlCheck registry response", "https://github.com/modelcontextprotocol/registry/issues/82#issuecomment-6711311079", "external_technical_reply", "HISTOR extras alignment; reported 30/30 is external author's measurement."),
 ("CrawlCheck OWASP response", "https://github.com/OWASP/secure-agent-playbook/issues/33#issuecomment-6712103956", "external_technical_reply", "Own text of response, separate from quoted owner material."),
 ("CrawlCheck specification", "https://crawlcheck.io/spec/mcp-lockfile#jcs-v1", "external_spec_alignment", "Published interface change; not full canonicalizer equivalence."),
 ("ACS avp9-nexus snapshot review", "https://github.com/GenAI-Security-Project/agent-control-standard/issues/38#issuecomment-6545176155", "external_dataset_analysis", "Third-party account's detailed analysis; 250 labels not re-run by baseline."),
 ("ACS Mayur021 code review", "https://github.com/GenAI-Security-Project/agent-control-standard/issues/38#issuecomment-6572123939", "external_code_discussion", "Code-reading statement and proposal discussion; no adopted standard."),
 ("AgentAvow response", "https://github.com/AgentAvow/AgentAvow/issues/240#issuecomment-6714769340", "external_technical_reply", "Request to link; no added backlink verified in baseline."),
 ("Industrial pinned dependency", "https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/main/aimarket-sentinel/requirements.txt", "external_source_dependency", "Git-pinned Hub source retained; old runtime endpoint was HTTP404 on Nov9."),
 ("Industrial federation adapter", "https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/main/gateway/aimarket-federation.mjs", "external_adapter_source", "Source compatibility is not current deployment."),
 ("RugSnare", "https://github.com/Paraphern/rugsnare", "external_research_reuse", "README cites HISTOR dataset/DOI; known historical case."),
 ("Witness technical reply", "https://lists.witness-network.org/mailman3/hyperkitty/list/participate@lists.witness-network.org/message/762ZAYCAXMZPHXAMX3UZ5OARJHJWCWVZ/", "external_technical_reply", "Nov4 staging admission; not production audit."),
 ("Witness staging log list", "https://staging.witness-network.org/log-list-10qps-4klogs.1", "external_configuration_reference", "Exact HISTOR key presence; not runtime application adoption."),
 ("IETF Du response", "https://mailarchive.ietf.org/arch/msg/dawn/GbumKwLL1oy3I7h7GFmgAkNJAkQ/", "external_technical_reply", "Read original reply before owner quotations; individual draft, not RFC."),
 ("IETF Linda response", "https://mailarchive.ietf.org/arch/msg/dawn/6m1_jcurI0F0_LadffO71f0d4m8/", "external_technical_reply", "Marketplace/bootstrap discussion; company endorsement not established."),
 ("IETF MDI draft", "https://datatracker.ietf.org/doc/draft-cui-dawn-mdi-model/", "external_document_acknowledgment", "Acknowledgment and selected changes; individual Internet-Draft."),
 ("Qiita Skillselion response", "https://qiita.com/qwezzy721/items/4dfe9dc2fbe9d69b1fb7#comment-a71ae02460f429b7606e", "external_technical_reply", "Oct24 cache/TTL discussion; owner article edits are not new external responses."),
 ("1gateway AIMarket", "https://1gateway.dev/market/modelmarket.dev", "automated_protocol_observation", "Published unpaid quote checks; not paid delivery."),
 ("LupaRiel AIMarket", "https://lupariel.com/fichas/aimarket-hub/", "automated_catalog_with_probe_claim", "Historical Oct30 unpaid probe; review dated Oct31."),
 ("VerifyMCP AIMarket", "https://verifymcp.io/servers/alexar76-aimarket-hub/modelmarket", "automated_protocol_observation", "Nov10 surface scan and tools inventory, not safety certification."),
 ("AgentRank Metis", "https://agentrank-ai.com/tool/alexar76--metis/", "automated_catalog", "Same operator as other AgentRank cards; no publication date established."),
 ("AgentRank Hub", "https://agentrank-ai.com/tool/alexar76--aimarket-hub/", "automated_catalog", "Catalog link, no installation or paid use established."),
 ("AgentRank Agent", "https://agentrank-ai.com/tool/alexar76--aimarket-agent/", "automated_catalog", "Catalog link, no installation or paid use established."),
 ("AgentRank Attested", "https://agentrank-ai.com/tool/alexar76--attested-memory/", "automated_catalog", "Known Oct30 card; not new Nov10."),
 ("AgentsShipped factory", "https://agentsshipped.com/l/alexar76-aicom", "catalog", "Visible May11 date semantics unknown; not assumed publication date."),
 ("Anclum plugins", "https://anclum.com/zh/s/alexar76-aimarket-plugins/", "aggregated_catalog", "README/awesome-derived; Chinese UI does not establish operator country."),
 ("TeckDeck cache churn", "https://teckdeck.io/posts/we-found-331-mcp-tool-list-changes-in-one-week-that-only-moved-a-date-each-one-costs-a-prompt-cache-write", "derived_summary_of_owner_article", "Exact Nov3 article; same known aggregator."),
 ("Gemivo cache churn", "https://ainews.gemivo.de/news/we-found-331-mcp-tool-list-changes-in-one-week-that-only-cmw03yqv3005", "redistribution_of_owner_article", "Own English article under German UI, not independent research."),
 ("Web Pulse scanner comparison", "https://wpnews.pro/news/we-ran-three-mcp-security-scanners-on-a-tool-poisoning-benchmark-and-986-real", "redistribution_of_owner_article", "Historical Oct9 comparison, not current scanner benchmark."),
 ("Hlido passport", "https://hlido.eu/passport/alexar76-aimarket-plugins/", "external_review_catalog", "Known Aug5 review; legal/compliance labels unverified."),
 ("APIs.io Attested", "https://apis.io/providers/attestedmemory-net/", "automated_api_profile", "Harvested registry profile; generated contracts/skills not adoption."),
 ("Agenstry marketplace", "https://agenstry.com/agents/modelmarket.dev", "automated_protocol_observation", "Directory direct probes; baseline last7d invocations zero."),
 ("Agent Economy Report", "https://agenteconomy.report/s/modelmarket.dev.json", "automated_market_observation", "Organic labels have owner-test contamination; method changed Nov2/8."),
 ("Agent402 seller index", "https://agent402.tools/api/index?seller=modelmarket.dev", "external_router_listing", "Eight paid routes marked dispatch-ineligible settlement_self_funded Nov9."),
 ("UseTested review", "https://usetested.com/v1/review?service=modelmarket.dev", "paid_measurement_bot_test", "One historical Oct27 test; review refresh not new purchase."),
 ("ShortformKit MCP index", "https://github.com/shortformkit/free-remote-mcp-servers/blob/main/data/servers.json", "automated_protocol_index", "Attested/domain/weather; protocol inventory, not tools/call."),
 ("ragmap EMPORION index", "https://github.com/khalidsaidi/ragmap/blob/main/data/servers.json", "automated_protocol_index", "EMPORION lastOk Nov9 and eight tools; business function use not established."),
 ("Hubwiz security article", "https://www.hubwiz.com/blog/agent-security-nine-incidents-six-controls/", "derived_technical_article", "Known Oct15 Chinese retelling; no independent rerun established."),
 ("Juejin security article", "https://juejin.cn/post/7696713457148952630", "derived_technical_article", "Known Oct15 retelling with historical WARDEN0.9 table."),
 ("Radyz HISTOR dataset", "https://radyz.cz/rychle-zpravy/histor-otevrel-dataset-zmen-nastroju-mcp-nikoli-seznam-skodlivych-serveru/", "derived_technical_article", "Known Oct22 dataset note, not runtime integration."),
]
records = []
for i, (label, url, kind, limit) in enumerate(CANDIDATES, 1):
    ev, refs = collect(url)
    records.append({"id": i, "label": label, "source_url": url, "classification": kind,
                    "ownership": "External account/site surface; operator independence or human identity not established unless noted by baseline.",
                    "scope_limit": limit, "baseline_primary_captures": ev,
                    "captured_own_target_references": refs,
                    "has_captured_html_href": any(x["form"] == "html_href" for x in refs),
                    "current_availability": "not_rechecked_by_baseline_agent", "novelty": "already_in_baseline"})
controls = [
    {"source_url": "https://vouch-protocol.com/agent-trust-index/", "classification": "mention_without_backlink", "scope_limit": "Six exact ecosystem rows, zero HTML href in those rows. DID/key checks, not behavior/safety."},
    {"source_url": "https://www.agent-router.org/agents", "classification": "search_only_candidate", "scope_limit": "Direct HTML app shell, current card not primary-confirmed."},
    {"source_url": "https://ainews.gemivo.de/", "classification": "false_positive_control", "scope_limit": "How to give an AI agent a record it can't rewrite originates with dev.to/datafund, not Attested Memory."},
    {"source_url": "https://modelcontextproblems.com/", "classification": "negative_control", "scope_limit": "No exact ecosystem identifiers found in saved Nov10 body; thematic similarity not attribution."},
]
(OUT / "baseline-candidates.json").write_text(json.dumps({"date_client": "2026-11-10", "baseline_reports": REPORTS,
    "candidate_pages": len(records), "candidates": records, "controls_not_backlinks": controls,
    "limitations": ["Local evidence inventory only; no network recheck performed.", "Target references retain href versus plain text/Markdown distinction.",
                    "For GitHub comments only matched comment body is extracted; quoted owner text can still occur within a comment and needs semantic review.",
                    "Source code URL literals are references, not necessarily HTML backlinks.", "Some report-backed sources have no matching capture URL in these bounded indexes; source report is the provenance, not fabricated primary evidence."]}, ensure_ascii=False, indent=2) + "\n")

counts = inventory["counts"]
summary = f"""# Локальная базовая линия для исследования внешних ссылок — 10 ноября 2026\n\nБазовая линия — утренний аудит 10 ноября и три аудита 9 ноября, перечисленные в `baseline-candidates.json`. Октябрьские отчеты нужны для истории, но не для объявления уже найденных ноябрьских ссылок новыми. Существующий `../report.ru.md` не перезаписан. Этот подпроход выполнял только локальные чтения: сетевых запросов нет.\n\n## Объекты поиска\n\nВ `scripts/satellite-map.yaml` **{counts['mapping_entries']} записей**: {counts['github_published_declared_entries']} с опубликованным статусом (явным или значением по умолчанию), {counts['github_unpublished_declared_entries']} с `github_published: false`. Из опубликованных две записи — wiki и одна — профиль. Остается **{counts['published_component_or_collection_entries_excluding_profile_and_wikis']} запись компонента или коллекции**. Это не число независимых продуктов, операторов или пользователей: есть семейства, исторический alias Emberline и общие репозитории. Существование remote заново не проверялось.\n\n`inventory.json` сохраняет все 60 записей с точной строкой исходника, домашними страницами и путями. Из выбранных поддерживаемых entry sources извлечено **{counts['own_public_hosts_in_selected_maintained_sources']} собственных публичных hostnames** с provenance. Источники: карта satellite, `scripts/github-io/index.html`, `ecosystem-landing/index.html`, `pingblip/README.md`, `pantheon/README.md`. Это не полный DNS/domain inventory. Дополнительно отмечены немаппированные публичные PANTHEON/Trace, PingBlip и исторический маркер Independent AI.\n\n## Что уже доказано базовой линией\n\nСильнейшие связи — совместимость extras HISTOR в спецификации/fixture CrawlCheck, независимые технические разборы ACS, witness staging admission, ответы участников DAWN и зависимость/adapter Industrial Platform. Разделены опубликованное утверждение чужого автора и то, что воспроизводил сам прежний аудит. В частности, 30/30 CrawlCheck — измерение автора; наш baseline сравнивал один fixture/record. Witness — staging, IETF — индивидуальный draft, а не принятый стандарт.\n\nАвтоматическое наблюдение интерфейсов подтверждают 1gateway, VerifyMCP, LupaRiel, ShortformKit и ragmap. Каталожные страницы AgentRank/AgentsShipped/Anclum и перепечатки TeckDeck/Gemivo/Web Pulse показывают обнаружимость и распространение. Эти виды связи не превращены в платящих клиентов или независимые runtime-интеграции.\n\nОчередь `baseline-candidates.json` содержит **{len(records)} отобранных внешних страниц/публичных артефактов** для текущей проверки source→target. Где найден сохраненный первичный ответ, приложены точный JSON index, raw path, UTC, HTTP status, SHA-256 и буквальные ссылки на собственные цели с различием HTML href и URL в тексте/Markdown. Некоторые технические контакты — упоминания/согласование интерфейса, а не backlink: этот предел сохранен явно.\n\n## Ошибки, которые нельзя повторять\n\n- Vouch: шесть точных упоминаний, но в строках нет HTML href; это не шесть backlinks.\n- AgentRouter: поисковый снимок при loading shell не подтверждает текущую карточку.\n- Исторические 404 Industrial endpoint не доказывают закрытие проекта; код/зависимость сохранялись.\n- Agent402: dispatch policy `settlement_self_funded` не равна недоступности прямого API.\n- AER organic counts включали собственный тестовый wallet и посредника, методика менялась; это не число независимых клиентов.\n- UseTested: один исторический платный measurement test от 27 октября; обновление review не означает новую покупку.\n- Own DEV posts, зеркала, пересказы и агрегаторы не являются независимыми повторными исследованиями.\n- Названия Metis/Gaia/Atlas/Histor/Warden без точной ссылки/identity marker неоднозначны.\n- HTTP 401/403/429, robots, CAPTCHA и app shell — неизвестный результат, не отсутствие упоминаний.\n- Локализация интерфейса не устанавливает страну оператора или клиента.\n\n## Унаследованные ограничения\n\nПубличная индексированная выборка, не весь интернет; закрытые группы, авторизованные социальные поиски и частный код не охвачены. Канонический target и актуальная доступность должны проверяться новым GET. Один оператор может иметь несколько страниц и несколько источников могут пересказывать один собственный оригинал. Число источников, ссылок, упоминаний и операторов не суммируется в число пользователей.\n"""
(OUT / "baseline-summary.md").write_text(summary)
print(json.dumps({"counts": counts, "candidate_pages": len(records), "capture_backed": sum(bool(x['baseline_primary_captures']) for x in records), "with_own_references": sum(bool(x['captured_own_target_references']) for x in records)}, ensure_ascii=False))
