"""Append six reviewed fresh PingBlip Shorts to native UTC publication slots.

Only the six new video IDs are ever mutated. Existing uploads and schedules are
read before and after publication. An unknown upload outcome blocks a retry.
"""
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
import time

import yaml
from snapshot import A, P, snapshot, u

R = P / 'v20-new-signal'
STATE = A / 'qa/publication-state.json'
PLAN = P / 'v5-week-one/publication-plan.json'
QUEUE = P / 'v5-week-one/queue-state.json'
UTC = dt.timezone.utc
NEW_ORDER = ['PB70', 'PB71', 'PB72', 'PB73', 'PB74', 'PB75']
CADENCE = {'timezone': 'UTC', 'dailyTimes': ['13:00', '19:00'],
           'fixedUtcAcrossDst': True, 'audienceTimezone': 'America/New_York'}


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def parse(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def stamp(value):
    return value.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def next_slot(after):
    day = after.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    for offset in range(3):
        for hour in [13, 19]:
            candidate = day + dt.timedelta(days=offset, hours=hour)
            if candidate > after:
                return candidate
    raise AssertionError('No following UTC slot')


def baseline():
    before = load(A / 'qa/youtube-before.json')
    assert before['channelId'] == u.EXPECTED_CHANNEL_ID
    return before


def fetch(youtube, ids):
    result = {}
    for start in range(0, len(ids), 50):
        response = youtube.videos().list(
            part='snippet,status,processingDetails,contentDetails',
            id=','.join(ids[start:start + 50])).execute()
        for video in response.get('items', []):
            assert video['snippet']['channelId'] == u.EXPECTED_CHANNEL_ID
            result[video['id']] = video
    assert set(result) == set(ids), 'A saved video ID is missing from the API'
    return result


def verify_existing(actual):
    """Allow native publication after its due time; never allow a moved slot."""
    now = dt.datetime.now(UTC)
    transitioned = []
    before_by = {video['id']: video for video in baseline()['videos']}
    assert set(before_by).issubset(actual), 'A preexisting video disappeared'
    for video_id, previous in before_by.items():
        current = actual[video_id]
        # publishedAt and thumbnails can change when YouTube publishes a video.
        for field in ['channelId', 'title', 'description', 'tags', 'categoryId',
                      'defaultLanguage', 'defaultAudioLanguage']:
            assert current['snippet'].get(field) == previous['snippet'].get(field), (video_id, field)
        old_status, new_status = previous['status'], current['status']
        if new_status == old_status:
            continue
        native_publication = (old_status.get('privacyStatus') == 'private'
                              and old_status.get('publishAt')
                              and parse(old_status['publishAt']) <= now
                              and new_status.get('privacyStatus') == 'public'
                              and not new_status.get('publishAt'))
        assert native_publication, (video_id, 'preexisting status changed')
        old_other = {key: value for key, value in old_status.items()
                     if key not in ['privacyStatus', 'publishAt']}
        new_other = {key: value for key, value in new_status.items()
                     if key not in ['privacyStatus', 'publishAt']}
        assert old_other == new_other, (video_id, 'preexisting status settings changed')
        transitioned.append(video_id)
    return transitioned


def prepare():
    assert not STATE.exists(), 'Resume the saved publication state instead of preparing twice'
    episodes = load(R / 'final/manifest.json')
    validation = load(A / 'qa/validation.json')
    assert {episode['id'] for episode in episodes} == set(NEW_ORDER)
    assert {row['id'] for row in validation} == set(NEW_ORDER)
    for episode in episodes:
        check = next(row for row in validation if row['id'] == episode['id'])
        assert episode['freshGameplay'] and episode['visualApproved']
        assert check['visualApproved'] and check['decodePassed']
        assert check['sha256'] == episode['sha256'] == hashlib.sha256((P / episode['file']).read_bytes()).hexdigest()
        assert episode['sources'], 'Fresh recording provenance is required'
        for source in episode['sources']:
            assert hashlib.sha256(Path(source['file']).read_bytes()).hexdigest() == source['sha256']
    capture = load(A / 'qa/capture/capture-summary.json')
    assert capture['completed'] and capture['freshSession'] and capture['noAdminAccess']
    before = baseline()
    now = dt.datetime.now(UTC)
    assert dt.timedelta(0) <= now - parse(before['checkedAt']) < dt.timedelta(hours=4), 'Refresh the read-only baseline before preparation'
    active = [video for video in before['videos']
              if video['status'].get('publishAt') and parse(video['status']['publishAt']) > now]
    assert all(video['status']['privacyStatus'] == 'private' for video in active)
    old_stamps = [video['status']['publishAt'] for video in active]
    assert len(old_stamps) == len(set(old_stamps)), 'Existing schedule has duplicate slots'
    assert all((parse(value).hour, parse(value).minute, parse(value).second) in [(13, 0, 0), (19, 0, 0)] for value in old_stamps)
    start = next_slot(max([now + dt.timedelta(minutes=30)] + [parse(value) for value in old_stamps]))
    log = u.load_log()
    plan = load(PLAN)
    meta = yaml.safe_load(u.META_PATH.read_text())
    assert not any(eid in log['shorts'] or eid in meta['episodes'] for eid in NEW_ORDER)
    assert not any(row['id'] in NEW_ORDER for row in plan)
    titles = {video['snippet']['title'] for video in before['videos']}
    state = {'createdAt': u.now(), 'channelId': u.EXPECTED_CHANNEL_ID,
             'cadence': CADENCE, 'order': NEW_ORDER, 'items': {},
             'existingScheduledAtPreparation': [
                 {'videoId': video['id'], 'title': video['snippet']['title'],
                  'publishAt': video['status']['publishAt']}
                 for video in sorted(active, key=lambda video: video['status']['publishAt'])]}
    when = start
    for eid in NEW_ORDER:
        episode = next(row for row in episodes if row['id'] == eid)
        title, description, _ = u.short_meta(episode, None)
        u.check_public_text(eid, title, description)
        assert title not in titles, 'A publication with this title already exists'
        titles.add(title)
        row = {key: episode[key] for key in ['id', 'title', 'file', 'sha256']}
        row.update(series='story', format=episode['kind'], publishAt=stamp(when),
                   scheduleTimezone='UTC', newYork=when.astimezone(ZoneInfo('America/New_York')).isoformat(),
                   moscow=when.astimezone(ZoneInfo('Europe/Moscow')).isoformat())
        assert row['publishAt'] not in old_stamps
        plan.append(row)
        meta['episodes'][eid] = {'title': episode['title'], 'description': episode['description'],
                                 'video': episode['file'], 'short_video': episode['file'],
                                 'tags': ['PingBlip', 'BrowserGame', 'CreatureCollector', episode['name']],
                                 'contains_synthetic_media': True}
        meta['upload_order'].append(eid)
        state['items'][eid] = {'new': True, 'phase': 'ready', 'row': row, 'videoId': None}
        when = next_slot(when)
    for relative in ['upload_log.json', 'upload_metadata.yaml',
                     'v5-week-one/publication-plan.json', 'v5-week-one/queue-state.json']:
        target = A / 'qa/before' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(P / relative, target)
    # Save resumable intent before any external writes. The existing plan rows
    # are preserved exactly; only the six new rows and metadata are appended.
    save(STATE, state)
    save(PLAN, plan)
    u.META_PATH.write_text(yaml.safe_dump(meta, allow_unicode=True, sort_keys=False))
    save(R / 'publication-plan.json', [state['items'][eid]['row'] for eid in NEW_ORDER])
    for eid in NEW_ORDER:
        print('PREPARED', eid, state['items'][eid]['row']['publishAt'], flush=True)


def upload(youtube, state):
    if state.get('nextUploadAttemptAt'):
        assert dt.datetime.now(UTC) >= parse(state['nextUploadAttemptAt']), 'Wait until ' + state['nextUploadAttemptAt']
    actual = {video['id']: video for video in snapshot(youtube)['videos']}
    verify_existing(actual)
    known_new = {item['videoId'] for item in state['items'].values() if item.get('videoId')}
    assert set(actual) == {video['id'] for video in baseline()['videos']} | known_new, 'Channel changed; inspect before continuing'
    meta = yaml.safe_load(u.META_PATH.read_text())
    for eid in NEW_ORDER:
        item = state['items'][eid]
        title, description, tags = u.short_meta(meta['episodes'][eid], None)
        if item.get('videoId'):
            # An interruption can occur after saving the accepted video ID but
            # before updating the shared log. Recover that local write only.
            log = u.load_log()
            logged = log['shorts'].get(eid)
            if logged:
                assert logged['videoId'] == item['videoId']
            else:
                assert actual[item['videoId']]['snippet']['title'] == title
                log['shorts'][eid] = {'videoId': item['videoId'], 'url': item['url'],
                                      'title': title, 'file': item['row']['file'],
                                      'privacy': 'private', 'uploadedAt': item['uploadedAt'],
                                      'captions': False, 'thumbnail': False, 'playlist': False}
                u.save_log(log)
            continue
        assert item['phase'] not in ['upload_started', 'unknown_upload_outcome'], 'Unknown upload outcome; inspect channel before retrying ' + eid
        path = P / item['row']['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['row']['sha256']
        u.check_public_text(eid, title, description)
        item.update(phase='upload_started', uploadStartedAt=u.now())
        save(STATE, state)
        try:
            video_id = u.upload_video(youtube, path, title, description, tags,
                                      meta['channel'], 'private', contains_synthetic_media=True)
        except Exception as error:
            limited = u.is_quota_error(error)
            item['phase'] = 'upload_limit' if limited else 'unknown_upload_outcome'
            if limited:
                state['uploadLimitObservedAt'] = u.now()
                state['nextUploadAttemptAt'] = (dt.datetime.now(UTC) + dt.timedelta(hours=24, minutes=10)).isoformat()
            save(STATE, state)
            if not limited:
                queue = load(QUEUE)
                queue['blockedUpload'] = {'id': eid, 'batch': R.name,
                                          'reason': 'Unknown upload outcome; inspect channel before retry to avoid duplicates.'}
                save(QUEUE, queue)
            raise
        item.update(videoId=video_id, phase='uploaded_private',
                    url='https://youtube.com/shorts/' + video_id, uploadedAt=u.now(),
                    syntheticDisclosureSentAt=u.now())
        save(STATE, state)
        log = u.load_log()
        log['shorts'][eid] = {'videoId': video_id, 'url': item['url'], 'title': title,
                              'file': item['row']['file'], 'privacy': 'private',
                              'uploadedAt': item['uploadedAt'], 'captions': False,
                              'thumbnail': False, 'playlist': False}
        u.save_log(log)
        print('UPLOADED', eid, video_id, flush=True)


def schedule(youtube, state):
    sys.path.insert(0, str(P / 'v5-week-one/source'))
    from manage_queue import schedule_video
    ids = [item['videoId'] for item in state['items'].values() if item.get('videoId')]
    assert ids, 'No uploaded videos to schedule'
    for attempt in range(36):
        actual = fetch(youtube, ids)
        assert not [video_id for video_id, video in actual.items()
                    if video['status'].get('uploadStatus') in ['failed', 'rejected']]
        pending = [video_id for video_id, video in actual.items()
                   if video.get('processingDetails', {}).get('processingStatus') != 'succeeded']
        if not pending:
            break
        print('PROCESSING', len(pending), flush=True)
        time.sleep(5)
    else:
        raise RuntimeError('Processing is pending; rerun schedule with these saved video IDs')
    # Only mutate saved IDs belonging to this batch, never preexisting videos.
    old_ids = {video['id'] for video in baseline()['videos']}
    for eid in NEW_ORDER:
        item = state['items'][eid]
        if not item.get('videoId'):
            continue
        assert item['videoId'] not in old_ids
        when = item['row']['publishAt']
        video = fetch(youtube, [item['videoId']])[item['videoId']]
        assert video['status']['privacyStatus'] == 'private'
        assert parse(when) > dt.datetime.now(UTC) + dt.timedelta(minutes=10)
        assert video['status'].get('publishAt') in [None, when], 'New video has an unexpected schedule'
        if video['status'].get('publishAt') != when:
            fields = ['privacyStatus', 'license', 'embeddable', 'publicStatsViewable',
                      'selfDeclaredMadeForKids', 'containsSyntheticMedia']
            status = {key: value for key, value in video['status'].items() if key in fields}
            status.update(privacyStatus='private', publishAt=when, containsSyntheticMedia=True)
            schedule_video(youtube, item['videoId'], status)
            item['syntheticDisclosureSentAt'] = u.now()
            save(STATE, state)
        for attempt in range(8):
            current = fetch(youtube, [item['videoId']])[item['videoId']]
            if current['status'].get('publishAt') == when:
                break
            time.sleep(2)
        assert current['status'].get('publishAt') == when
        item.update(phase='scheduled', scheduleVerifiedAt=u.now())
        save(STATE, state)
        log = u.load_log()
        log['shorts'][eid].update(publishAt=when, scheduleTimezone='UTC',
                                   scheduledLocal=item['row']['newYork'], scheduledMoscow=item['row']['moscow'])
        u.save_log(log)
        print('SCHEDULED', eid, when, flush=True)


def verify(youtube, state, partial=False):
    after = snapshot(youtube)
    actual = {video['id']: video for video in after['videos']}
    transitioned = verify_existing(actual)
    before_ids = {video['id'] for video in baseline()['videos']}
    new_ids = {item['videoId'] for item in state['items'].values() if item.get('videoId')}
    assert set(actual) == before_ids | new_ids
    assert new_ids.isdisjoint(before_ids)
    if not partial:
        assert len(new_ids) == len(NEW_ORDER)
    meta = yaml.safe_load(u.META_PATH.read_text())
    checks, pending = [], []
    for eid in NEW_ORDER:
        item = state['items'][eid]
        row = item['row']
        if not item.get('videoId'):
            assert partial
            pending.append({'id': eid, 'file': row['file'], 'publishAt': row['publishAt']})
            continue
        video = actual[item['videoId']]
        assert item['phase'] == 'scheduled'
        assert video['status']['privacyStatus'] == 'private' and video['status'].get('publishAt') == row['publishAt']
        assert video.get('processingDetails', {}).get('processingStatus') == 'succeeded'
        title, description, tags = u.short_meta(meta['episodes'][eid], None)
        assert video['snippet']['title'] == title
        assert video['snippet']['description'] == u.with_profile_cta(description)
        assert set(video['snippet'].get('tags', [])) == set(tags)
        assert item.get('syntheticDisclosureSentAt')
        assert video['status'].get('containsSyntheticMedia') is not False
        checks.append({'id': eid, 'new': True, 'videoId': video['id'], 'title': title,
                       'url': item['url'], 'publishAt': row['publishAt'], 'newYork': row['newYork'],
                       'processing': 'succeeded', 'syntheticDisclosureRequested': True,
                       'syntheticDisclosureReadback': video['status'].get('containsSyntheticMedia')})
    future = sorted([video for video in actual.values()
                     if video['status'].get('publishAt') and parse(video['status']['publishAt']) > dt.datetime.now(UTC)],
                    key=lambda video: video['status']['publishAt'])
    stamps = [video['status']['publishAt'] for video in future]
    assert len(stamps) == len(set(stamps)), 'Duplicate native publication slots'
    receipt = {'checkedAt': u.now(), 'channelId': u.EXPECTED_CHANNEL_ID, 'cadence': CADENCE,
               'newUploads': len(checks), 'rescheduledExisting': 0,
               'capturedBaselineDistinctVideos': len(before_ids), 'channelDistinctVideos': len(actual),
               'allCapturedPreviousTitlesDescriptionsTagsPreserved': True,
               'allPreviousPublicationSchedulesPreserved': True,
               'previousVideosWithUnchangedStatus': len(before_ids) - len(transitioned),
               'nativePublicationTransitions': transitioned, 'scheduled': checks,
               'existingScheduled': state['existingScheduledAtPreparation'],
               'futureQueue': [{'videoId': video['id'], 'title': video['snippet']['title'],
                                'publishAt': video['status']['publishAt'], 'url': 'https://youtube.com/shorts/' + video['id']}
                               for video in future]}
    if partial:
        receipt.update(pendingUploads=pending, nextUploadAttemptAt=state.get('nextUploadAttemptAt'))
    suffix = 'partial-' if partial else ''
    save(A / ('qa/youtube-' + suffix + 'after.json'), after)
    save(A / ('qa/youtube-' + suffix + 'verification.json'), receipt)
    save(R / ('publication-' + suffix + 'receipt.json'), receipt)
    if not partial:
        state['verifiedAt'] = u.now()
        save(STATE, state)
        queue = load(QUEUE)
        queue.update(lastVerifiedAt=u.now(), lastAppendedBatch=R.name,
                     scheduleTimezone='UTC', allPublished=False)
        queue.setdefault('events', []).append({'at': u.now(), 'event': 'fresh_batch_appended',
                                               'newUploads': len(checks), 'rescheduledExisting': 0,
                                               'scheduledTotal': len(future), 'receipt': str(R / 'publication-receipt.json')})
        save(QUEUE, queue)
    print('VERIFIED' + (' PARTIAL' if partial else ''), len(checks),
          'new native schedules;', len(future), 'total future videos; previous schedules preserved', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'publish', 'schedule', 'verify', 'partial', 'verify-partial'])
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    else:
        youtube = u.get_youtube(open_browser=False)
        u.assert_pingblip(u.whoami(youtube), for_upload=True)
        state = load(STATE)
        assert state['channelId'] == u.EXPECTED_CHANNEL_ID
        if args.action == 'publish':
            upload(youtube, state)
            schedule(youtube, state)
        elif args.action in ['schedule', 'partial']:
            schedule(youtube, state)
        verify(youtube, state, partial=args.action in ['partial', 'verify-partial'])
