"""Verify the continuing filming profile and every fresh public action receipt."""
import datetime as dt
import hashlib
import json
from pathlib import Path

from capture import A, P, R, Q

ORDER = [f'PB{number}' for number in range(76, 82)]
PETS = {'pigeon': 'pigeon-king', 'egg': 'soft-egg', 'moth': 'sprinkle-moth'}
CITIES = {'kyoto': ('Kyoto', 35.0116, 135.7681),
          'capetown': ('Cape Town', -33.9249, 18.4241)}


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    capture = load(Q / 'capture-summary.json')
    assert capture['completed'] and capture['freshSession'] and capture['noAdminAccess']
    assert capture['resumedOwnFilmingProfile'] and capture['newProfileCreated'] is False
    assert capture['frames'] > 500
    marks = load(Q / 'marks-absolute.json')
    assert marks['recording_start'] == capture['recordingStartUnix'] < marks['end']
    initial = load(Q / 'initial-owned.json')
    previous = load(A.parent / 'pingblip-series-2026-11-09/qa/capture/final_bench.json')
    final = load(Q / 'final_bench.json')
    initial_by = {pet['id']: pet for pet in initial['creatures']}
    previous_by = {pet['id']: pet for pet in previous['creatures']}
    final_by = {pet['id']: pet for pet in final['creatures']}
    assert not initial.get('anonymous') and set(initial_by) == set(previous_by)
    assert len(initial_by) == 3 and len(final_by) == 5
    assert initial['creditsMilli'] == previous['creditsMilli'] == 430
    for pet_id, pet in initial_by.items():
        assert pet['speciesId'] == previous_by[pet_id]['speciesId']
        assert pet['feedCount'] == previous_by[pet_id]['feedCount']
    resumed = load(Q / 'session-resumed.json')
    assert resumed['httpStatus'] == 200 and resumed['ownDocumentedProfile']
    assert resumed['newProfileCreated'] is False

    receipts = {}
    for path in sorted(Q.glob('*-result.json')):
        recorded = load(path)
        name = path.name.removesuffix('-result.json')
        result = recorded['result']
        assert recorded['httpStatus'] == 200, name
        assert marks['recording_start'] <= recorded['recordedAt'] <= marks['end'], name
        assert result.get('ok'), name
        if '_scan' in name:
            assert result['roster'], name
        receipts[name] = result
    expected_fixed = {key + suffix for key in PETS for suffix in ['_select', '_feed']}
    expected_fixed.update(['house_claim', 'kyoto_catch', 'capetown_catch'])
    scans = {name: result for name, result in receipts.items() if '_scan' in name}
    assert set(receipts) == expected_fixed | set(scans), 'Unexpected or missing public actions'
    assert 2 <= len(scans) <= 4
    assert set(scans).issubset({city + suffix for city in CITIES for suffix in ['_scan', '_scan_air']})

    feed_progress = []
    fed_ids = set()
    for key, species_id in PETS.items():
        original = next(pet for pet in initial_by.values() if pet['speciesId'] == species_id)
        before = load(Q / (key + '-before.json'))
        after = load(Q / (key + '-after.json'))
        bench_before = load(Q / (key + '_bench_before.json'))
        bench_after = load(Q / (key + '_bench_after.json'))
        fed = receipts[key + '_feed']['creature']
        assert original['id'] == before['id'] == after['id'] == fed['id']
        assert before['feedCount'] == original['feedCount']
        assert fed['feedCount'] == before['feedCount'] + 1 == after['feedCount']
        assert next(pet for pet in bench_before['creatures'] if pet['id'] == original['id']) == before
        assert next(pet for pet in bench_after['creatures'] if pet['id'] == original['id']) == after
        assert final_by[original['id']]['feedCount'] == after['feedCount']
        assert not after['asleep'] and not receipts[key + '_feed'].get('justEvolved')
        assert bench_after['creditsMilli'] == bench_before['creditsMilli'] - 50
        fed_ids.add(fed['id'])
        feed_progress.append({'key': key, 'speciesId': species_id,
                              'before': before['feedCount'], 'after': after['feedCount']})
    assert fed_ids == set(initial_by)

    grant = receipts['house_claim']
    assert grant['kind'] == 'house' and grant['grantedMilli'] == 250
    assert load(Q / 'house_bench.json')['creditsMilli'] - load(Q / 'moth_bench_after.json')['creditsMilli'] == 250
    caught_ids, choices = set(), {}
    for city, (label, latitude, longitude) in CITIES.items():
        choice = load(Q / (city + '-choice.json'))
        scan_key = choice['scanKey']
        assert scan_key in scans and scan_key.startswith(city + '_scan')
        assert choice['layer'] == scans[scan_key]['layer']
        caught = receipts[city + '_catch']
        pet = caught['creature']
        assert not caught.get('already') and pet['id'] not in initial_by
        assert pet['id'] not in caught_ids
        assert choice['speciesId'] == pet['speciesId']
        assert any(row['id'] == pet['speciesId'] and not row['owned'] for row in scans[scan_key]['roster'])
        assert final_by[pet['id']]['speciesId'] == pet['speciesId']
        assert pet['feedCount'] == final_by[pet['id']]['feedCount'] == 0
        caught_ids.add(pet['id'])
        choices[label] = {'coordinates': [latitude, longitude], 'scanKey': scan_key,
                          'layer': choice['layer'], 'speciesId': choice['speciesId'],
                          'name': choice['name']}
    assert set(final_by) == set(initial_by) | caught_ids
    expected_balance = initial['creditsMilli'] + grant['grantedMilli'] - len(fed_ids) * 50 - len(scans) * 30 - len(caught_ids) * 80
    assert final['creditsMilli'] == expected_balance

    raw = R / 'capture/raw-vertical.mp4'
    raw_sha = sha(raw)
    def recorded_hashes(value):
        # Historical packs contain both a single episode object and arrays;
        # source hashes also occur under sourceSHA256 in the earlier format.
        if isinstance(value, dict):
            return set().union(*(recorded_hashes(child) for child in value.values()))
        if isinstance(value, list):
            return set().union(*(recorded_hashes(child) for child in value))
        if isinstance(value, str) and len(value) == 64 and all(char in '0123456789abcdef' for char in value.lower()):
            return {value.lower()}
        return set()
    prior_hashes = set()
    for path in P.glob('v*/final/manifest.json'):
        if path.parent.parent == R:
            continue
        prior_hashes.update(recorded_hashes(load(path)))
    assert raw_sha not in prior_hashes, 'Raw footage matches an earlier batch'
    manifest = load(R / 'final/manifest.json')
    assert len(manifest) == 6 and {episode['id'] for episode in manifest} == set(ORDER)
    assert len({episode['sha256'] for episode in manifest}) == 6
    source_hashes = {}
    for episode in manifest:
        assert episode['freshGameplay']
        assert episode['sha256'] == sha(P / episode['file'])
        assert episode['sha256'] not in prior_hashes
        assert Path(episode['sources'][0]['file']) == raw and episode['sources'][0]['sha256'] == raw_sha
        for source in episode['sources']:
            if source['file'] not in source_hashes:
                source_hashes[source['file']] = sha(source['file'])
            assert source_hashes[source['file']] == source['sha256']
    report = {'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
              'freshRecording': True, 'newPublicFilmingProfile': False,
              'resumedOwnFilmingProfile': True, 'initialProfileMatchesPreviousBatch': True,
              'recordingStartUnix': capture['recordingStartUnix'], 'frames': capture['frames'],
              'sourceSha256': raw_sha, 'actualHatches': 0, 'actualFeeds': len(fed_ids),
              'actualDailyGrants': 1, 'actualScans': len(scans), 'actualNewCatches': len(caught_ids),
              'initialOwnedCreatures': len(initial_by), 'finalOwnedCreatures': len(final_by),
              'initialPips': initial['creditsMilli'], 'finalPips': final['creditsMilli'],
              'expectedFinalPips': expected_balance, 'feedProgress': feed_progress,
              'successfulFreshReceipts': sorted(receipts), 'noEarlierFootage': True,
              'noAdminAccess': True, 'remoteMapChoices': choices}
    (A / 'qa/freshness-verification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print('Verified fresh continuing profile:', len(fed_ids), 'feeds, one grant,', len(scans),
          'scans, two new catches;', initial['creditsMilli'], 'to', final['creditsMilli'], 'pips')


if __name__ == '__main__':
    main()
