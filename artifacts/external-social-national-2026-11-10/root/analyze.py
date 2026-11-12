"""Analyze saved public reads only; does not perform network requests."""
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

def write(name, data):
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

queries = []
for path in sorted(HERE.glob('search-*.json')):
    data = json.loads(path.read_text())
    for query in data['queries']:
        queries.append({'query': query, 'response_file': path.name,
                        'request_sent_not_exhaustive_coverage': True,
                        'batch_partially_blocked': path.name == 'search-11.json',
                        'noncanonical_brand_probe': 'CiteDesks' in query or 'EmberlineDesk' in query})
write('query-index.json', queries)

http = []
for path in sorted(HERE.glob('plan-*-index.json')):
    http.extend(json.loads(path.read_text()))
checks = []
extracts = []
for row in http:
    body = (HERE / row['file']).read_bytes()
    checks.append({'file': row['file'], 'status': row['status'],
                   'length_matches': len(body) == row['bytes'],
                   'sha256_matches': hashlib.sha256(body).hexdigest() == row['sha256'],
                   'complete': not row['truncated']})
    soup = BeautifulSoup(body, 'html.parser')
    links = [{'text': a.get_text(' ', strip=True)[:120], 'href': a['href']}
             for a in soup.find_all('a', href=True)
             if any(marker in a['href'] for marker in ['alexar76', 'modelmarket.dev', 'attestedmemory.net'])]
    dates = [x.get('datetime') for x in soup.find_all('time', datetime=True)]
    extracts.append({'file': row['file'], 'source_url': row['url'],
                     'title': soup.title.get_text(' ', strip=True) if soup.title else None,
                     'explicit_identity_links': links, 'time_elements_not_all_article_dates': dates})
write('http-index.json', http)
write('primary-links.json', extracts)
write('verification.json', {'captured_at': datetime.now(timezone.utc).isoformat(),
                           'checks': checks, 'all_passed': all(c['length_matches'] and c['sha256_matches'] and c['complete'] for c in checks)})

sources = [REPO / 'docs/growth'] + [p for p in (REPO / 'artifacts').iterdir()
           if p.is_dir() and p.name.startswith(('external', 'ecosystem')) and p != HERE.parent]
def previous(url):
    result = subprocess.run(['rg', '-l', '-F', '--glob', '*.json', '--glob', '*.md',
                             '--glob', '*.txt', url, *map(str, sources)], capture_output=True, text=True)
    if result.returncode not in [0, 1]:
        raise RuntimeError(result.stderr)
    return [str(Path(p).relative_to(REPO)) for p in result.stdout.splitlines()]

findings = [
 {'id': 'info-agent-ia-gateway', 'source_url': 'https://info-agent-ia.com/en/mcp/aimarket/',
  'component': 'AIMarket MCP Gateway / Metis', 'classification': 'directory_metadata_and_setup_summary',
  'novelty': 'prior_exact_search_candidate_now_primary_read', 'new_independent_mention': False,
  'evidence': 'HTTP 200; explicit alexar76/aimarket-mcp and Glama hrefs; 60/C metadata score; updated November 10, 2026.',
  'limits': 'Registry/README-derived description and generic setup advice. No invocation trace, external project config or authored benchmark. Publisher editorial identity claims not verified.'},
 {'id': 'wpnews-hub', 'source_url': 'https://wpnews.pro/news/i-opened-a-live-agent-marketplace-the-receipts-were-the-product',
  'component': 'Hub / Bridges / MCP', 'classification': 'republication_of_owner_article',
  'novelty': 'prior_exact_search_candidate_now_primary_read', 'new_independent_mention': False,
  'published_at': '2026-09-15T11:19:16Z',
  'evidence': 'HTTP 200; datePublished time; links marked original to DEV alexar76; absolute href to modelmarket.dev.',
  'limits': 'A new primary read in this pass, not a new article or independent test. Other November time elements are related articles.'},
 {'id': 'jonkum-aggregators', 'source_url': 'https://www.jonkum.in/mcp/aggregators',
  'component': 'AIMarket MCP Packager / plugins', 'classification': 'derived_catalog',
  'novelty': 'known_primary_source_since_2026-10-26', 'new_independent_mention': False,
  'evidence': 'HTTP 200; alexar76/aimarket-plugins, pip install aimarket-mcp-packager, GitHub href.',
  'limits': 'Text says aggregation from registry/reference repository/community. No installed user config. The .in suffix does not establish an Indian operator.'},
 {'id': 'mcp-pub-gateway', 'source_url': 'https://mcp.pub/servers/aimarket-mcp/',
  'component': 'AIMarket MCP Gateway', 'classification': 'catalog_public_evidence_assessment',
  'novelty': 'known_primary_source_since_2026-10-26', 'new_independent_mention': False,
  'evidence': 'HTTP 200; maintainer alexar76, repository href, 6.5/10 assessment, example AIMARKET_MCP_KEY and Metis preset config.',
  'limits': 'Publisher says based on collected public evidence. An installation example on a directory is not a foreign project integration.'}
]
for row in findings:
    row['previous_exact_url_files'] = previous(row['source_url'])
write('findings.json', findings)
write('summary.json', {'web_query_strings': len(queries), 'web_batches': 11,
                       'partially_blocked_batch_query_strings': 4,
                       'noncanonical_brand_probe_strings': 2,
                       'native_primary_gets': len(http),
                       'http_statuses': {'200': sum(r['status'] == 200 for r in http)},
                       'web_open_cache_misses': 3,
                       'new_independent_mentions': 0, 'new_runtime_integrations': 0,
                       'prior_search_candidates_now_read': 2,
                       'known_catalog_reconfirmations': 2,
                       'query_index': 'query-index.json', 'findings': 'findings.json'})
print(json.dumps({'queries': len(queries), 'http_gets': len(http), 'integrity_passed': all(c['sha256_matches'] and c['length_matches'] and c['complete'] for c in checks), 'previous_exact_urls': {x['id']:len(x['previous_exact_url_files']) for x in findings}}, ensure_ascii=False))
