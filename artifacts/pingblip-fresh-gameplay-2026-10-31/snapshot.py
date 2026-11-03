"""Read the verified PingBlip channel; keep evidence inside aicom."""
from pathlib import Path
import json, sys

A = Path(__file__).resolve().parent
P = A.parents[2] / 'PromoMaterials/blip/youtube-season-something-pinged'
sys.path.insert(0, str(P))
import upload_youtube as u

def snapshot(y):
    me = u.whoami(y)
    u.assert_pingblip(me, for_upload=True)
    ch = y.channels().list(part='contentDetails', mine=True).execute()['items'][0]
    playlist = ch['contentDetails']['relatedPlaylists']['uploads']
    ids, token = [], None
    while True:
        r = y.playlistItems().list(part='contentDetails', playlistId=playlist, maxResults=50, pageToken=token).execute()
        ids.extend(i['contentDetails']['videoId'] for i in r.get('items', []))
        token = r.get('nextPageToken')
        if not token:
            break
    # Uploads-playlist pagination can repeat or omit entries while native
    # scheduling reorders the list. Supplement it with known official IDs and
    # the preserved baseline, then read every distinct video ID directly.
    listed_count=len(ids)
    ids.extend(row['videoId'] for eid,row in u.load_log()['shorts'].items()
               if not eid.startswith('S64') and row.get('videoId'))
    for name in ['youtube-before.json','youtube-before-supplement.json']:
        baseline=A/'qa'/name
        if baseline.exists():
            ids.extend(v['id'] for v in json.loads(baseline.read_text())['videos'])
    ids=list(dict.fromkeys(ids))
    videos = []
    for start in range(0, len(ids), 50):
        videos.extend(y.videos().list(part='snippet,status,processingDetails,contentDetails', id=','.join(ids[start:start+50])).execute().get('items', []))
    assert all(v['snippet']['channelId'] == u.EXPECTED_CHANNEL_ID for v in videos)
    return {'checkedAt': u.now(), 'channelId': me['id'],
            'playlistListedEntries':listed_count,'directlyReadDistinctVideos':len(videos),'videos': videos}

if __name__ == '__main__':
    y = u.get_youtube(open_browser=False)
    result = snapshot(y)
    target = A/'qa/youtube-before.json'
    assert not target.exists(), 'Preserve the initial snapshot'
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print('Channel', result['channelId'], 'videos', len(result['videos']))
    for v in result['videos']:
        if v['status'].get('publishAt'):
            print(v['id'], v['status']['publishAt'], v['snippet']['title'])
