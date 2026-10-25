#!/usr/bin/env python3
"""Independently reconcile saved Linux decisions; no guard execution or network."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def rows(name, size):
    result = {}
    for line in (ROOT / name).read_text().splitlines():
        row = json.loads(line)
        if row['size'] != size:
            continue
        key = (row['key'], row['kind'], row.get('profile'), row.get('i'), row.get('case'))
        assert key not in result, key
        result[key] = row
    return result


def aggregate(variant, group):
    return {field: sum(p[group][field] for p in variant['partitions'].values())
            for field in ('total', 'pass', 'ask', 'deny')}


baseline = read('baseline/full/replay-results.json')
final = read('final/final-8/replay-results.json')
general = read('final/candidate-8/replay-results.json')
for report, decisions in [(baseline, 'baseline/full/decisions.jsonl'),
                          (final, 'final/final-8/decisions.jsonl'),
                          (general, 'final/candidate-8/decisions.jsonl')]:
    assert digest(ROOT / decisions) == report['decisionsSha256']

download = read('final/final-download-manifest.json')
for file in download['files']:
    path = ROOT / 'final' / file['path']
    assert path.stat().st_size == file['bytes'] and digest(path) == file['sha256']

base_corpus = read('baseline/full/corpus.json')
final_corpus = read('final/final-8/corpus.json')
assert base_corpus['files'] == final_corpus['files']
assert set(f['sha256'] for f in base_corpus['files'] if f['partition'] == 'calibration').isdisjoint(
    f['sha256'] for f in base_corpus['files'] if f['partition'] == 'holdout')

paired = {}
transitions = Counter()
intrinsic = Counter()
improved_by_format = Counter()
for size in (6, 7, 8):
    paired[str(size)] = rows('baseline/full/decisions.jsonl', size)
reference = paired['8']
candidate = rows('final/final-8/decisions.jsonl', 8)
assert len(reference) == 29760 and reference.keys() == candidate.keys()
for other in [paired['6'], paired['7'], candidate]:
    assert other.keys() == reference.keys()
    assert all(other[k]['inputSha256'] == reference[k]['inputSha256'] for k in reference)
for key, old in reference.items():
    new = candidate[key]
    transitions[f"{old['kind']}/{old.get('profile', 'all')}/{old['decision']}->{new['decision']}"] += 1
    if old['kind'] == 'benign':
        assert old['decision'] == new['decision']
    else:
        assert old['decision'] != 'pass' and new['decision'] != 'pass'
        assert old['decision'] != 'deny' or new['decision'] == 'deny'
        intrinsic[f"{old['detectorOnly']}->{new['detectorOnly']}"] += 1
        if old['decision'] == 'ask' and new['decision'] == 'deny':
            improved_by_format[old['key'].split('/')[1]] += 1

bc = {r['id']: r for r in baseline['collisions']}
fc = {r['id']: r for r in final['collisions']}
assert len(bc) == 31 and bc.keys() == fc.keys()
assert all(bc[k]['bodySha256'] == fc[k]['bodySha256'] and bc[k]['key'] == fc[k]['key'] for k in bc)
assert all(bc[k]['decisions']['8'] == fc[k]['decisions']['8'] for k in bc)
collision_decisions = {str(size): dict(Counter(r['decisions'][str(size)] for r in bc.values())) for size in (6, 7, 8)}
collision_decisions['final8'] = dict(Counter(r['decisions']['8'] for r in fc.values()))

regressions = {}
for label in ('baseline', 'general', 'final'):
    regressions[label] = {r['id']: r for r in read(f'final/regressions-{label}/regressions.json')['results']}
    assert regressions[label]['known-benign-7-collision']['decisions'] == {'6': 'deny', '7': 'deny', '8': 'pass'}
assert regressions['baseline']['late-digit-embedded-8']['decisions']['8'] == 'ask'
assert regressions['final']['late-digit-embedded-8']['decisions']['8'] == 'deny'
assert regressions['baseline']['reviewed-public-word-year-config']['decisions']['8'] == 'pass'
assert regressions['general']['reviewed-public-word-year-config']['decisions']['8'] == 'deny'
assert regressions['final']['reviewed-public-word-year-config']['decisions']['8'] == 'pass'

compat = read('final/final-8/index-compatibility.json')
assert compat['keys'] == 960 and all(r['lost'] == 0 and r['after'] >= r['before'] for r in compat['rows'])
pipeline = read('final/final-pipeline-status.json')
assert len(pipeline) == 6 and all(row['exitCode'] == 0 for row in pipeline)
gate = read('final/final-redteam.json')['results']
assert len(gate) == 28 and not any(r['outcome'] == 'delivered' for r in gate)
egress = read('final/final-credential-egress.json')
assert all(p['attacks']['automatic'] == 0 and p['benign']['hardDenial'] == 0 for p in egress['profiles'])

table = {}
for label, report, size in [('6', baseline, '6'), ('7', baseline, '7'), ('8', baseline, '8'),
                            ('final8', final, '8'), ('rejectedGeneral8', general, '8')]:
    value = report['variants'][size]
    table[label] = {group: aggregate(value, group) for group in ('strictDefault', 'exactReviewedPublic', 'attacks', 'detectorOnly')}
    table[label]['partitions'] = {part: {g: counts[g] for g in ('attacks', 'detectorOnly')}
                                  for part, counts in value['partitions'].items()}
    table[label]['attackByFormat'] = {fmt: {f: sum(p['attackByFormat'][fmt][f] for p in value['partitions'].values())
                                          for f in ('total', 'pass', 'ask', 'deny')}
                                     for fmt in value['partitions']['calibration']['attackByFormat']}

per_case = {}
for case in baseline['variants']['8']['partitions']['calibration']['attackByCase']:
    per_case[case] = {}
    for label, report, size in [('6', baseline, '6'), ('7', baseline, '7'), ('8', baseline, '8'), ('final8', final, '8')]:
        per_case[case][label] = {profile: {f: sum(p['attackByCase'][case][profile][f]
                                                for p in report['variants'][size]['partitions'].values())
                                         for f in ('total', 'pass', 'ask', 'deny')}
                                for profile in ('guard', 'detector')}

result = {
    'schema': 'warden.threshold-independent-analysis/v1',
    'pairedInputsPerVariant': len(reference), 'identicalInputDigestsAcrossBaselineThresholdsAndFinal': True,
    'uniqueBenignRequests': 7680, 'benignProfiles': 2, 'attackRequests': 14400,
    'corpus': {k: read('baseline/full/corpus-results.json')[k] for k in ('files', 'excerpts', 'normalizedCharacters', 'summary')},
    'finalCorpus': {k: read('final/final-8/corpus-results.json')[k] for k in ('files', 'excerpts', 'normalizedCharacters', 'summary')},
    'table': table, 'pairedTransitions': dict(transitions), 'detectorOnlyTransitions': dict(intrinsic),
    'newHardDenialsByFormat': dict(improved_by_format),
    'collisionEnrichedControls': collision_decisions,
    'indexCompatibility': {'keys': compat['keys'], 'lostFingerprints': 0,
                           'keysWithMoreFingerprints': sum(r['after'] > r['before'] for r in compat['rows']),
                           'before': sum(r['before'] for r in compat['rows']), 'after': sum(r['after'] for r in compat['rows'])},
    'attackByCase': per_case, 'regressions': regressions,
    'releaseGate': {'scenarios': len(gate), 'answerOnly': sum(r['outcome'] in ('noted', 'rechecked') for r in gate),
                    'toolAttackDelivered': 0},
    'notes': ['Counters concern constructed fixtures, not a production false-positive rate.',
              'Known collision controls are deliberately selected, not an unbiased sample.',
              'All empirical guard measurements ran in networkless Linux containers; local unit tests are separate.'],
}
(ROOT / 'analysis.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({k: result[k] for k in ('pairedInputsPerVariant', 'pairedTransitions', 'detectorOnlyTransitions',
                                        'newHardDenialsByFormat', 'collisionEnrichedControls', 'indexCompatibility')}, indent=2))
