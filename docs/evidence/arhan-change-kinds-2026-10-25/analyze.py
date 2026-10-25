#!/usr/bin/env python3
"""Classify a frozen public HISTOR dataset from full content-addressed tool lists.

No server/package execution or network. Dataset is read-only; scratch SQLite is private
to the output directory. Run empirical analysis in the isolated Linux container.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import zlib

MISSING = object()
MANIFEST_SHA = 'a7bfc9e09ab9782157ad6c7a4bb136477609746a7e7e6f9c6695ea2012e926fc'
BASE_CUTOFF = '2026-09-24T23:59:59Z'
MAP_SCHEMAS = {'properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas'}
SINGLE_SCHEMAS = {'items', 'additionalItems', 'additionalProperties', 'contains', 'not', 'if', 'then', 'else',
                  'propertyNames', 'unevaluatedProperties', 'unevaluatedItems', 'contentSchema'}
ARRAY_SCHEMAS = {'allOf', 'anyOf', 'oneOf', 'prefixItems'}
ANNOTATIONS = {'title', 'examples', '$comment'}
FLAG_NAMES = ('composition', 'tool_description', 'parameter_description', 'input_schema', 'output_schema',
              'schema_contract', 'schema_order', 'schema_annotation', 'descriptions_only', 'tool_descriptions_only')
KIND_RANK = {'unchanged': 0, 'whitespace': 1, 'numeric': 2, 'text': 3}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def exact(a, b):
    """JSON equality with type-sensitive booleans/numbers and order-insensitive objects."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(exact(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b


def text_kind(a, b):
    if a == b:
        return 'unchanged'
    old, new = re.sub(r'\s+', '', a), re.sub(r'\s+', '', b)
    if old == new:
        return 'whitespace'

    def mask(text):
        # Typed tokens avoid confusing a literal placeholder with an actual digit run.
        return tuple(('number',) if part.isdecimal() else ('text', part)
                     for part in re.split(r'(\d+)', text) if part)

    return 'numeric' if mask(old) == mask(new) else 'text'


def permutation(a, b):
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
        return False
    aa, bb = [dump(x) for x in a], [dump(x) for x in b]
    return len(set(aa)) == len(aa) and len(set(bb)) == len(bb) and set(aa) == set(bb)


def snippet(a, b):
    if a is MISSING or b is MISSING:
        return {'old': '<absent>' if a is MISSING else dump(a)[:240],
                'new': '<absent>' if b is MISSING else dump(b)[:240]}
    if isinstance(a, str) and isinstance(b, str):
        offset = 0
        while offset < min(len(a), len(b)) and a[offset] == b[offset]:
            offset += 1
        start = max(0, offset - 70)
        return {'old': a[start:start + 240], 'new': b[start:start + 240], 'offset': start}
    return {'old': dump(a)[:240], 'new': dump(b)[:240]}


def compare_toolsets(old, new):
    flags = {k: False for k in FLAG_NAMES}
    details = []
    top_kinds, all_kinds = [], []
    before = {t['name']: t for t in old}
    after = {t['name']: t for t in new}
    if len(before) != len(old) or len(after) != len(new):
        raise ValueError('duplicate tool name')
    added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
    flags['composition'] = bool(added or removed)

    def record(kind, tool, path, a, b):
        if len(details) < 12:
            details.append({'kind': kind, 'tool': tool, 'path': path, **snippet(a, b)})

    def description(a, b, tool, path, top=False):
        flags['tool_description' if top else 'parameter_description'] = True
        # Missing versus a textual annotation is a description edit. Empty-presence changes
        # are conservatively retained as text, rather than disappearing from the comparison.
        if (a is MISSING or isinstance(a, str)) and (b is MISSING or isinstance(b, str)):
            kind = text_kind('' if a is MISSING else a, '' if b is MISSING else b)
            if kind == 'unchanged':
                kind = 'text'
        else:
            flags['schema_contract'] = True
            kind = 'text'
        all_kinds.append(kind)
        if top:
            top_kinds.append(kind)
        record('description_' + kind, tool, path, a, b)

    def schema(a, b, tool, path, is_schema=True):
        if exact(a, b):
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(a.keys() | b.keys()):
                x, y = a.get(key, MISSING), b.get(key, MISSING)
                if exact(x, y):
                    continue
                child = path + '/' + key.replace('~', '~0').replace('/', '~1')
                if is_schema and key == 'description':
                    description(x, y, tool, child)
                elif is_schema and key in ANNOTATIONS:
                    flags['schema_annotation'] = True
                    record('schema_annotation', tool, child, x, y)
                elif is_schema and key in MAP_SCHEMAS and isinstance(x, dict) and isinstance(y, dict):
                    # Map keys are literal property/definition names, not schema keywords.
                    for name in sorted(x.keys() | y.keys()):
                        xx, yy = x.get(name, MISSING), y.get(name, MISSING)
                        member = child + '/' + name.replace('~', '~0').replace('/', '~1')
                        if xx is MISSING or yy is MISSING:
                            flags['schema_contract'] = True
                            record('schema_contract', tool, member, xx, yy)
                        else:
                            schema(xx, yy, tool, member, True)
                elif is_schema and key in SINGLE_SCHEMAS:
                    if key == 'items' and isinstance(x, list) and isinstance(y, list):
                        schema_array(x, y, tool, child)
                    elif isinstance(x, (dict, bool)) and isinstance(y, (dict, bool)):
                        schema(x, y, tool, child, True)
                    else:
                        flags['schema_contract'] = True
                        record('schema_contract', tool, child, x, y)
                elif is_schema and key in ARRAY_SCHEMAS and isinstance(x, list) and isinstance(y, list):
                    schema_array(x, y, tool, child)
                elif is_schema and key in ('required', 'enum') and permutation(x, y) and (
                        key == 'enum' or all(isinstance(v, str) for v in x + y)):
                    flags['schema_order'] = True
                    record('schema_order', tool, child, x, y)
                elif is_schema and key == 'dependencies' and isinstance(x, dict) and isinstance(y, dict):
                    for name in sorted(x.keys() | y.keys()):
                        xx, yy = x.get(name, MISSING), y.get(name, MISSING)
                        if isinstance(xx, (dict, bool)) and isinstance(yy, (dict, bool)):
                            schema(xx, yy, tool, child + '/' + name, True)
                        elif not exact(xx, yy):
                            flags['schema_contract'] = True
                            record('schema_contract', tool, child + '/' + name, xx, yy)
                else:
                    # Includes defaults, unknown extension keywords, $schema, $id and $ref.
                    # Never recursively interpret literal default/enum/example values as schemas.
                    flags['schema_contract'] = True
                    record('schema_contract', tool, child, x, y)
        else:
            flags['schema_contract'] = True
            record('schema_contract', tool, path, a, b)

    def schema_array(a, b, tool, path):
        if len(a) != len(b):
            flags['schema_contract'] = True
            record('schema_contract', tool, path, a, b)
        for index, (x, y) in enumerate(zip(a, b)):
            schema(x, y, tool, path + '/' + str(index), True)

    for name in sorted(before.keys() & after.keys()):
        a, b = before[name], after[name]
        da, db = a.get('description', ''), b.get('description', '')
        if not exact(da, db):
            description(da, db, name, '/description', True)
        for field, flag in [('inputSchema', 'input_schema'), ('outputSchema', 'output_schema')]:
            x, y = a.get(field, MISSING), b.get(field, MISSING)
            if not exact(x, y):
                flags[flag] = True
                schema(x, y, name, '/' + field, True)
    desc_kind = max(all_kinds, key=KIND_RANK.get, default='unchanged')
    top_kind = max(top_kinds, key=KIND_RANK.get, default='unchanged')
    any_desc = flags['tool_description'] or flags['parameter_description']
    other = any(flags[k] for k in ('composition', 'schema_contract', 'schema_order', 'schema_annotation'))
    flags['descriptions_only'] = any_desc and not other
    flags['tool_descriptions_only'] = flags['tool_description'] and not (
        flags['composition'] or flags['input_schema'] or flags['output_schema'])
    if flags['composition']:
        primary = 'composition'
    elif flags['schema_contract']:
        primary = 'schema_contract'
    elif desc_kind == 'text':
        primary = 'description_text'
    elif desc_kind == 'numeric':
        primary = 'description_numeric'
    elif flags['schema_order']:
        primary = 'schema_order'
    elif flags['schema_annotation']:
        primary = 'schema_annotation'
    elif desc_kind == 'whitespace':
        primary = 'description_whitespace'
    else:
        primary = 'unchanged'
    return {'primary': primary, 'flags': flags, 'tool_description_kind': top_kind,
            'description_kind': desc_kind, 'added': added, 'removed': removed, 'details': details}


def rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        for line in handle:
            yield json.loads(line)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def aggregate(records):
    primary = Counter(r['primary'] for r in records)
    per = defaultdict(list)
    for row in records:
        per[row['serverId']].append(row)
    flags_event = {name: sum(r['flags'].get(name, False) for r in records) for name in FLAG_NAMES}
    flags_server = {name: sum(any(r['flags'].get(name, False) for r in group) for group in per.values()) for name in FLAG_NAMES}
    partition = Counter()
    for group in per.values():
        observed = [r['tool_description_kind'] for r in group if r['tool_description_kind'] != 'unchanged']
        if any(r['primary'] == 'unknown' for r in group):
            category = 'incomplete'
        elif 'text' in observed:
            category = 'any_text_beyond_digits_whitespace'
        elif 'numeric' in observed:
            category = 'numeric_and_optional_whitespace_only'
        elif 'whitespace' in observed:
            category = 'whitespace_only'
        else:
            category = 'no_tool_description_change'
        partition[category] += 1
    return {'transitions': len(records), 'servers': len(per), 'primary': dict(sorted(primary.items())),
            'flagsTransitions': flags_event, 'flagsServers': flags_server,
            'toolDescriptionKinds': dict(Counter(r['tool_description_kind'] for r in records)),
            'descriptionKinds': dict(Counter(r['description_kind'] for r in records)),
            'serverToolDescriptionPartition': dict(partition)}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    assert file_hash(args.data / 'manifest.json') == MANIFEST_SHA, 'Wrong snapshot'
    manifest = json.loads((args.data / 'manifest.json').read_text())
    hashes = {}
    for name in ('servers.jsonl.gz', 'changes.jsonl.gz', 'toolsets.jsonl.gz'):
        hashes[name] = file_hash(args.data / name)
        assert hashes[name] == manifest['files'][name]['sha256'], name
    print('All snapshot SHA-256 checks passed', flush=True)
    servers = {r['id']: r for r in rows(args.data / 'servers.jsonl.gz')}
    base = {key for key, r in servers.items() if r['transport'] != 'stdio' and not r['delisted']
            and r['toolSetDigest'] is not None and r['firstPinned'] is not None and r['firstPinned'] <= BASE_CUTOFF}
    changes, cohort, legacy_numeric, legacy_whitespace = [], set(), 0, []
    for raw in rows(args.data / 'changes.jsonl.gz'):
        summary = json.loads(raw['summaryJson'])
        modified = summary.get('modified') or []
        desc = any('description' in (t.get('fields') or {}) for t in modified)
        fields = {field for t in modified for field in (t.get('fields') or {})}
        if not summary.get('added') and not summary.get('removed') and fields == {'description'}:
            edits = [op[1] for t in modified for op in t['fields']['description'] if op[0] in ('+', '-')]
            if edits and all(re.fullmatch(r'[\s\d.,:\-/]*', e) for e in edits):
                if any(re.search(r'\d', e) for e in edits):
                    legacy_numeric += 1
                else:
                    legacy_whitespace.append(raw['id'])
        if raw['serverId'] in base:
            if desc:
                cohort.add(raw['serverId'])
            changes.append({k: v for k, v in raw.items() if k not in ('summaryJson', 'labelId', 'fromSubjectDigest', 'toSubjectDigest')})
            changes[-1].update({'summaryFull': summary.get('detail') == 'full', 'summaryToolDescription': desc,
                               'summaryInputSchema': any('inputSchema' in (t.get('fields') or {}) for t in modified),
                               'summaryOutputSchema': any('outputSchema' in (t.get('fields') or {}) for t in modified),
                               'summaryComposition': bool(summary.get('added') or summary.get('removed'))})
    assert len(base) == 10929 and len(cohort) == 2036 and len(changes) == 10543
    selected = [c for c in changes if c['serverId'] in cohort]
    assert len(selected) == 7319 and sum(c['summaryToolDescription'] for c in selected) == 5482
    assert legacy_numeric == 2719 and len(legacy_whitespace) == 6
    wanted = {c[field] for c in changes for field in ('fromToolSetDigest', 'toToolSetDigest') if c[field]}
    scratch = args.out / '.toolsets.sqlite'
    assert not scratch.exists(), 'Refuse to overwrite prior scratch'
    db = sqlite3.connect(scratch)
    db.execute('PRAGMA journal_mode=OFF')
    db.execute('CREATE TABLE blobs(digest TEXT PRIMARY KEY, value BLOB NOT NULL)')
    from histor.subject import tool_set_digest
    import histor.subject
    loaded = 0
    for index, raw in enumerate(rows(args.data / 'toolsets.jsonl.gz'), 1):
        if raw['digest'] not in wanted:
            continue
        tools = json.loads(raw['toolsJson'])
        actual, canonical = tool_set_digest(tools)
        assert actual == raw['digest'], 'Content-address mismatch: ' + raw['digest']
        db.execute('INSERT INTO blobs VALUES(?,?)', (actual, zlib.compress(dump(canonical).encode(), 3)))
        loaded += 1
        if loaded % 1000 == 0:
            db.commit()
            print(f'Loaded and digest-verified {loaded}/{len(wanted)} relevant toolsets, file row {index}', flush=True)
    db.commit()
    found = {r[0] for r in db.execute('SELECT digest FROM blobs')}
    missing = sorted(wanted - found)
    print(f'Toolsets ready: {loaded}, missing: {len(missing)}', flush=True)

    @lru_cache(maxsize=8)
    def get(digest):
        row = db.execute('SELECT value FROM blobs WHERE digest=?', (digest,)).fetchone()
        return json.loads(zlib.decompress(row[0])) if row else None

    records = []
    mismatches = []
    for index, c in enumerate(sorted(changes, key=lambda c: (c['serverId'], c['observedAt'], c['id'])), 1):
        before, after = get(c['fromToolSetDigest']), get(c['toToolSetDigest'])
        if before is None or after is None:
            result = {'primary': 'unknown', 'flags': {}, 'tool_description_kind': 'unknown',
                      'description_kind': 'unknown', 'added': [], 'removed': [], 'details': []}
        else:
            result = compare_toolsets(before, after)
            for raw_flag, summary_flag in [('tool_description', 'summaryToolDescription'), ('input_schema', 'summaryInputSchema'),
                                           ('output_schema', 'summaryOutputSchema'), ('composition', 'summaryComposition')]:
                if result['flags'][raw_flag] != c[summary_flag]:
                    mismatches.append({'id': c['id'], 'field': raw_flag, 'raw': result['flags'][raw_flag], 'summary': c[summary_flag]})
        records.append({**c, **result, 'cohort2036': c['serverId'] in cohort})
        if index % 1000 == 0:
            print(f'Compared {index}/{len(changes)} events', flush=True)
    group = [r for r in records if r['cohort2036']]
    desc_group = [r for r in group if r['summaryToolDescription']]
    by_server = defaultdict(list)
    for row in group:
        by_server[row['serverId']].append(row)
    net_rows = []
    for key, sequence in sorted(by_server.items()):
        first, last = sequence[0], sequence[-1]
        before, after = get(first['fromToolSetDigest']), get(last['toToolSetDigest'])
        pairs = list(zip(sequence, sequence[1:]))
        known_pairs = [(x, y) for x, y in pairs if x['toToolSetDigest'] and y['fromToolSetDigest']]
        gaps = sum(x['toToolSetDigest'] != y['fromToolSetDigest'] for x, y in known_pairs)
        if before is None or after is None:
            net = {'primary': 'unknown', 'flags': {}, 'tool_description_kind': 'unknown', 'description_kind': 'unknown'}
        else:
            net = compare_toolsets(before, after)
        net_rows.append({'serverId': key, 'name': servers[key]['name'], 'endpoint': servers[key]['endpoint'],
                         'events': len(sequence), 'firstAt': first['observedAt'], 'lastAt': last['observedAt'],
                         'fromToolSetDigest': first['fromToolSetDigest'], 'toToolSetDigest': last['toToolSetDigest'],
                         'chainGaps': gaps, 'knownAdjacentPairs': len(known_pairs),
                         'unknownAdjacentPairs': len(pairs) - len(known_pairs), **net})
    record_file = args.out / 'transitions.jsonl'
    with record_file.open('w') as f:
        for row in records:
            f.write(dump(row) + '\n')
    with (args.out / 'servers.jsonl').open('w') as f:
        for row in net_rows:
            f.write(dump(row) + '\n')
    examples = {}
    for row in group:
        examples.setdefault(row['primary'], [])
        if len(examples[row['primary']]) < 3:
            examples[row['primary']].append({**row, 'name': servers[row['serverId']]['name'],
                                            'publicChangeUrl': f"https://histor.modelmarket.dev/api/v1/changes/{row['id']}"})
    report = {'schema': 'histor.change-kinds-study/v1', 'startedAt': started, 'finishedAt': datetime.now(timezone.utc).isoformat(),
              'manifestSha256': MANIFEST_SHA, 'inputSha256': hashes, 'snapshotCreatedAt': manifest['createdAt'],
              'changesFrom': manifest['changesFrom'], 'changesUntil': manifest['changesUntil'],
              'baseCutoff': BASE_CUTOFF, 'baseServers': len(base),
              'baseFullChangedServers': len({c['serverId'] for c in changes if c['summaryFull']}),
              'baseFullTransitions': sum(c['summaryFull'] for c in changes),
              'cohort2036': aggregate(group), 'toolDescriptionEvents2036': aggregate(desc_group),
              'baseAllEvents': aggregate(records), 'firstToLast2036': aggregate(net_rows),
              'serverChainsWithGaps': sum(r['chainGaps'] > 0 for r in net_rows),
              'knownAdjacentPairs': sum(r['knownAdjacentPairs'] for r in net_rows),
              'unknownAdjacentPairs': sum(r['unknownAdjacentPairs'] for r in net_rows),
              'legacyWholeSnapshotNumericEvents': legacy_numeric, 'legacyWhitespaceEventIds': legacy_whitespace,
              'requiredToolsets': len(wanted), 'verifiedToolsets': loaded, 'missingToolsets': missing,
              'rawSummaryFlagMismatches': mismatches, 'transitionFileSha256': file_hash(record_file),
              'canonicalizerModuleSha256': file_hash(Path(histor.subject.__file__)),
              'scriptSha256': file_hash(Path(__file__)), 'python': sys.version, 'examples': examples,
              'notes': ['Categories are lexical/field changes, not safety or semantic-equivalence verdicts.',
                        'Independent field flags overlap; primary bins do not.',
                        'Formatting in serialized JSON and tool/object key order is already excluded by the core digest.',
                        'Only core name/description/inputSchema/outputSchema fields are measured.',
                        'First/last compares the earliest recorded prechange and latest recorded postchange in this snapshot.']}
    (args.out / 'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    (args.out / 'manifest.json').write_text((args.data / 'manifest.json').read_text())
    db.close()
    scratch.unlink()
    print(json.dumps({k: report[k] for k in ('cohort2036', 'toolDescriptionEvents2036', 'firstToLast2036', 'requiredToolsets',
                                           'verifiedToolsets', 'missingToolsets', 'rawSummaryFlagMismatches')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
