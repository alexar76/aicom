#!/usr/bin/env python3
"""Read-only verification of PingBlip's 80 models and every shipped preview copy.

Default: local inventory/manifests only. Add --live after all three deployments.
The live check downloads public assets to memory, hashes their decoded contents,
and saves evidence only in this script's directory. It never authenticates or writes
remotely. Model URLs use the exact ?v=<content hash> format used by SculptedModel.
"""
import argparse
import concurrent.futures
import datetime as dt
import gzip
import hashlib
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PINGBLIP = REPO / 'pingblip'
FORGE = PINGBLIP / 'memeforge'
GAME = PINGBLIP / 'web'
WORLD = PINGBLIP / 'world'
ORIGINS = {
    'forge': 'https://forge.pingblip.com',
    'game': 'https://pingblip.com',
    'world': 'https://world.pingblip.com',
}
HEADER_KEYS = (
    'content-type', 'content-length', 'content-encoding', 'cache-control',
    'etag', 'last-modified', 'age', 'date', 'expires', 'vary', 'via', 'server',
    'cf-cache-status', 'x-cache', 'x-cache-hits', 'surrogate-control',
    'cdn-cache-control', 'x-content-type-options',
)
TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
TYPE_OPTIONS = {
    'model': {'model/gltf-binary', 'application/octet-stream'},
    'preview': {'image/webp'},
    'og': {'image/jpeg'},
    'manifest': {'application/json', 'text/json'},
}
ROUTE_EVIDENCE = [
    'pingblip/deploy/nginx/pingblip.conf: three public HTTPS vhosts proxy to their respective apps',
    'pingblip/memeforge/Dockerfile: COPY . . includes memeforge/public/models and public/dex',
    'pingblip/web/Dockerfile: copies memeforge/public/models and world/public/dex into game public/',
    'pingblip/world/Dockerfile: COPY world . includes world/public/dex; no world models copy',
    'pingblip/web/next.config.ts: /models/:path* rewrite fallback to Forge',
    'pingblip/memeforge/src/components/three/SculptedModel.tsx: /models/<id>.glb?v=<content hash>',
    'pingblip/memeforge/scripts/render-dex.mjs: Forge and World webps, World dex/og jpgs, Forge rendered-from manifest',
]


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_record(file):
    data = file.read_bytes()
    return {'path': str(file.relative_to(REPO)), 'bytes': len(data), 'sha256': sha256(data)}


def read_json(file, errors):
    try:
        value = json.loads(file.read_text())
        if not isinstance(value, dict):
            raise ValueError('expected JSON object')
        return value
    except (OSError, ValueError) as error:
        errors.append(f'{file.relative_to(REPO)}: {error}')
        return {}


def inventory():
    errors = []
    roster_source = (FORGE / 'src/data/mascots.ts').read_text()
    ids = re.findall(r'\{\s*id:\s*"([a-z0-9-]+)"', roster_source)
    if len(ids) != 80 or len(set(ids)) != 80:
        errors.append(f'expected 80 distinct mascot IDs, found {len(ids)} entries / {len(set(ids))} distinct')
    ids = sorted(set(ids))
    forge_versions = read_json(FORGE / 'src/data/model-versions.json', errors)
    game_versions = read_json(GAME / 'src/data/model-versions.json', errors)
    rendered_from = read_json(FORGE / 'public/dex/rendered-from.json', errors)
    for label, manifest in [('forge model versions', forge_versions), ('game model versions', game_versions), ('rendered-from', rendered_from)]:
        missing, extra = sorted(set(ids) - manifest.keys()), sorted(manifest.keys() - set(ids))
        if missing or extra:
            errors.append(f'{label}: missing={missing}, extra={extra}')
    assets = []
    files = []
    for asset_id in ids:
        record = {'id': asset_id, 'copies': {}}
        definitions = {
            'forge-model': (FORGE / 'public/models' / (asset_id + '.glb'), 'model', 'forge', f'/models/{asset_id}.glb'),
            'game-model': (GAME / 'public/models' / (asset_id + '.glb'), 'model', 'game', f'/models/{asset_id}.glb'),
            'forge-preview': (FORGE / 'public/dex' / (asset_id + '.webp'), 'preview', 'forge', f'/dex/{asset_id}.webp'),
            'game-preview': (GAME / 'public/dex' / (asset_id + '.webp'), 'preview', 'game', f'/dex/{asset_id}.webp'),
            'world-preview': (WORLD / 'public/dex' / (asset_id + '.webp'), 'preview', 'world', f'/dex/{asset_id}.webp'),
            'game-og': (GAME / 'public/dex/og' / (asset_id + '.jpg'), 'og', 'game', f'/dex/og/{asset_id}.jpg'),
            'world-og': (WORLD / 'public/dex/og' / (asset_id + '.jpg'), 'og', 'world', f'/dex/og/{asset_id}.jpg'),
        }
        for copy, (file, kind, site, route) in definitions.items():
            try:
                local = file_record(file)
                record['copies'][copy] = local
                files.append({'id': asset_id, 'copy': copy, 'kind': kind, 'site': site, 'route': route, 'local': local, 'assetClass': 'roster'})
            except OSError as error:
                errors.append(f'{copy} {asset_id}: {error}')
        copies = record['copies']
        for kind, labels in [('model', ['forge-model', 'game-model']), ('preview', ['forge-preview', 'game-preview', 'world-preview']), ('og', ['game-og', 'world-og'])]:
            hashes = {copies[label]['sha256'] for label in labels if label in copies}
            if len(hashes) != 1:
                errors.append(f'{asset_id}: local {kind} copies differ or all missing')
        if 'forge-model' in copies:
            version = copies['forge-model']['sha256'][:10]
            record['expectedModelVersion'] = version
            for label, manifest in [('forge model versions', forge_versions), ('game model versions', game_versions), ('rendered-from', rendered_from)]:
                if manifest.get(asset_id) != version:
                    errors.append(f'{asset_id}: {label} contains {manifest.get(asset_id)!r}, expected {version}')
        assets.append(record)
    eyes = []
    expected_eyes = {'dot', 'googly', 'jewel', 'slit', 'spiral', 'tired'}
    eye_ids = {file.stem for file in (FORGE / 'public/models/eyes').glob('*.glb')}
    if eye_ids != expected_eyes:
        errors.append(f'eye model roster: expected {sorted(expected_eyes)}, found {sorted(eye_ids)}')
    for eye_id in sorted(expected_eyes):
        eye = {'id': eye_id, 'copies': {}}
        for site, app in [('forge', FORGE), ('game', GAME)]:
            copy = site + '-eyes'
            try:
                local = file_record(app / 'public/models/eyes' / (eye_id + '.glb'))
                eye['copies'][copy] = local
                # Eye variants currently load plain URLs; --both-model-urls also
                # checks the content-hash form for these auxiliary assets.
                files.append({'id': 'eyes/' + eye_id, 'copy': copy, 'kind': 'model',
                              'site': site, 'route': '/models/eyes/' + eye_id + '.glb',
                              'local': local, 'assetClass': 'eyes', 'modelUrlMode': 'plain'})
            except OSError as error:
                errors.append(f'{copy} {eye_id}: {error}')
        if len({value['sha256'] for value in eye['copies'].values()}) != 1:
            errors.append(f'{eye_id}: Forge/game eye copies differ or all missing')
        eyes.append(eye)
    try:
        local_manifest = file_record(FORGE / 'public/dex/rendered-from.json')
        files.append({'id': 'rendered-from', 'copy': 'forge-rendered-from', 'kind': 'manifest', 'site': 'forge', 'route': '/dex/rendered-from.json', 'local': local_manifest, 'assetClass': 'manifest'})
    except OSError as error:
        errors.append(f'rendered-from file: {error}')
    return {'ids': ids, 'count': len(ids), 'assets': assets, 'auxiliaryEyes': eyes, 'errors': errors, 'manifests': {
        'forgeModelVersions': forge_versions, 'gameModelVersions': game_versions, 'renderedFrom': rendered_from,
    }}, files


def request_job(job, args):
    headers = {'User-Agent': 'PingBlipAssetVerifier/1.0 (read-only deployment verification)', 'Accept-Encoding': 'identity'}
    if args.revalidate:
        headers['Cache-Control'] = 'no-cache'
    url = ORIGINS[job['site']] + job['route']
    if job['kind'] == 'model' and job.get('modelUrlMode') != 'plain':
        url += '?v=' + job['local']['sha256'][:10]
    result = {key: job[key] for key in ('id', 'copy', 'kind', 'site', 'route')}
    result['assetClass'] = job['assetClass']
    result.update({'url': url, 'expectedSha256': job['local']['sha256'], 'expectedBytes': job['local']['bytes'], 'attempts': []})
    for attempt in range(args.attempts):
        started = time.monotonic()
        entry = {'startedAt': utc_now()}
        transient = False
        try:
            request = urllib.request.Request(url, headers=headers, method='GET')
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                entry['status'] = response.status
                entry['finalUrl'] = response.url
                entry['headers'] = {key: response.headers.get(key) for key in HEADER_KEYS if response.headers.get(key) is not None}
                # The extra ceiling prevents an erroneous route returning an unbounded body.
                limit = max(4 * 1024 * 1024, job['local']['bytes'] * 3)
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise ValueError(f'response exceeds byte ceiling {limit}')
                encoding = response.headers.get('Content-Encoding', 'identity').strip().lower()
                if encoding == 'gzip':
                    body = gzip.decompress(raw)
                elif encoding == 'deflate':
                    body = zlib.decompress(raw)
                elif encoding in ('identity', ''):
                    body = raw
                else:
                    raise ValueError(f'unsupported content encoding despite identity request: {encoding}')
                entry['wireBodyBytes'] = len(raw)
                entry['bodyBytes'] = len(body)
                entry['sha256'] = sha256(body)
                mime = response.headers.get('Content-Type', '').split(';', 1)[0].lower().strip()
                entry['contentTypeOk'] = mime in TYPE_OPTIONS[job['kind']]
                entry['hashMatches'] = entry['sha256'] == job['local']['sha256']
                entry['lengthMatches'] = len(body) == job['local']['bytes']
                entry['originMatches'] = urllib.parse.urlsplit(response.url).netloc == urllib.parse.urlsplit(ORIGINS[job['site']]).netloc
                entry['ok'] = all(entry.get(key) for key in ('contentTypeOk', 'hashMatches', 'lengthMatches', 'originMatches')) and response.status == 200
        except urllib.error.HTTPError as error:
            entry['status'] = error.code
            entry['headers'] = {key: error.headers.get(key) for key in HEADER_KEYS if error.headers.get(key) is not None}
            entry['error'] = f'HTTP {error.code} {error.reason}'
            transient = error.code in TRANSIENT_STATUS
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError, zlib.error) as error:
            entry['error'] = str(error)
            transient = isinstance(error, (urllib.error.URLError, TimeoutError, socket.timeout, OSError))
        entry['elapsedSeconds'] = round(time.monotonic() - started, 3)
        result['attempts'].append(entry)
        if entry.get('ok') or not transient or attempt + 1 == args.attempts:
            break
        time.sleep(min(2, .75 * (attempt + 1)))
    result['ok'] = bool(result['attempts'][-1].get('ok'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='fetch all supported public asset copies after deployment')
    parser.add_argument('--both-model-urls', action='store_true', help='verify both plain and content-hash forms for all model URLs (adds 172 GETs)')
    parser.add_argument('--concurrency', type=int, default=4, choices=range(1, 9), metavar='1..8')
    parser.add_argument('--timeout', type=float, default=30, help='per-request timeout seconds')
    parser.add_argument('--attempts', type=int, default=2, choices=range(1, 4), metavar='1..3')
    parser.add_argument('--revalidate', action='store_true', help='send Cache-Control: no-cache (default checks ordinary responses)')
    parser.add_argument('--output-name', help='JSON report filename inside this evidence directory')
    args = parser.parse_args()
    output_name = args.output_name or ('live-assets.json' if args.live else 'local-assets.json')
    if Path(output_name).name != output_name or not output_name.endswith('.json'):
        parser.error('--output-name must be a simple .json filename')
    started = time.monotonic()
    local, jobs = inventory()
    report = {'startedAt': utc_now(), 'scope': '80 roster models plus 6 eye variants; all supported Forge/game/World model, preview and OG copies',
              'origins': ORIGINS, 'sourceRouteEvidence': ROUTE_EVIDENCE, 'local': local,
              'options': {key: getattr(args, key) for key in ('live', 'both_model_urls', 'concurrency', 'timeout', 'attempts', 'revalidate')},
              'live': {'performed': False, 'results': []}}
    print(f'Local inventory: {local["count"]} roster models / {len(local["auxiliaryEyes"])} eye variants, {len(jobs) - 1} binary copies; {len(local["errors"])} error(s)', flush=True)
    for error in local['errors']:
        print('LOCAL FAIL: ' + error, flush=True)
    if args.live and not local['errors']:
        if args.both_model_urls:
            jobs += [{**job,
                      'copy': job['copy'] + ('-versioned' if job.get('modelUrlMode') == 'plain' else '-plain'),
                      'modelUrlMode': 'versioned' if job.get('modelUrlMode') == 'plain' else 'plain'}
                     for job in jobs if job['kind'] == 'model']
        report['live']['performed'] = True
        report['live']['plannedRequests'] = len(jobs)
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(request_job, job, args) for job in jobs]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
                if not result['ok']:
                    entry = result['attempts'][-1]
                    print(f'LIVE FAIL: {result["copy"]} {result["id"]} status={entry.get("status")} error={entry.get("error")} hashMatches={entry.get("hashMatches")}', flush=True)
                elif len(results) % 40 == 0 or len(results) == len(jobs):
                    print(f'Live assets: {len(results)}/{len(jobs)} checked', flush=True)
        results.sort(key=lambda row: (row['site'], row['kind'], row['id'], row['copy']))
        report['live']['results'] = results
        report['live']['passed'] = sum(row['ok'] for row in results)
        report['live']['failed'] = len(results) - report['live']['passed']
        summary = {}
        for row in results:
            group = summary.setdefault(row['copy'], {'checked': 0, 'passed': 0, 'failed': 0})
            group['checked'] += 1
            group['passed' if row['ok'] else 'failed'] += 1
        report['live']['groups'] = summary
    report['completedAt'] = utc_now()
    report['elapsedSeconds'] = round(time.monotonic() - started, 3)
    report['ok'] = not local['errors'] and (not args.live or report['live']['performed'] and not report['live'].get('failed', 0))
    output = HERE / output_name
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Report: {output}', flush=True)
    if args.live and report['live']['performed']:
        print(f'Live result: {report["live"]["passed"]}/{report["live"]["plannedRequests"]} asset URLs match local SHA256 and content types', flush=True)
    print('PASS' if report['ok'] else 'FAIL', flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
