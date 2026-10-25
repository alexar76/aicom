"""Remove three requested DEV badges while preserving the detailed AI disclosures.

Explicit human instruction: remove badges for Martin, Kartik and Raju; retain jkming.
No GitHub operation, new publication or comment submission.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / 'badge-removal-2026-10-25'
TOPICS = {'kartik': 4914093, 'martin': 4914123, 'raju': 4914201}
HEADER = '**AI disclosure — Fully Autonomous:**'
NEW_HEADER = '**AI disclosure:**'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    assert sys.argv[1:] in (['plan'], ['apply'])
    spec = importlib.util.spec_from_file_location('owned_devto', ROOT / 'devto_publish.py')
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    assert api.request('/api/users/me')['username'] == 'alexar76'
    FOLDER.mkdir(exist_ok=True)
    plan_path = FOLDER / 'plan.json'
    if sys.argv[1] == 'plan':
        assert not plan_path.exists(), 'Preserve the reviewed plan'
        changes = []
        for topic, article_id in TOPICS.items():
            old = api.get_article(article_id)
            assert old['user']['username'] == 'alexar76' and old['published_at']
            assert old['ai_disclosure_level'] == 'fully_autonomous'
            body = old['body_markdown']
            assert body.count(HEADER) == 1 and 'AI agents prepared' in body
            new_body = body.replace(HEADER, NEW_HEADER, 1)
            (FOLDER / f'{topic}.before.json').write_text(json.dumps(old, ensure_ascii=False, indent=2) + '\n')
            (FOLDER / f'{topic}.proposed.md').write_text(new_body)
            changes.append({'topic': topic, 'id': article_id, 'url': old['url'],
                            'oldBodySha256': digest(body), 'newBodySha256': digest(new_body),
                            'oldLevel': 'fully_autonomous', 'newLevel': 'not_disclosed',
                            'oldHeader': HEADER, 'newHeader': NEW_HEADER})
        plan_path.write_text(json.dumps({'author': 'alexar76', 'changes': changes,
                             'preserveArticleId': 4914122,
                             'note': 'Only remove UI badge and its name in the heading; preserve detailed AI provenance.'}, indent=2) + '\n')
        print(plan_path.read_text())
        return
    plan = json.loads(plan_path.read_text())
    assert plan['author'] == 'alexar76'
    protected_before = api.get_article(4914122)
    assert protected_before['ai_disclosure_level'] == 'fully_autonomous'
    result = []
    for change in plan['changes']:
        assert TOPICS[change['topic']] == change['id']
        before = api.get_article(change['id'])
        new_body = (FOLDER / f"{change['topic']}.proposed.md").read_text()
        assert digest(new_body) == change['newBodySha256'] and 'AI agents prepared' in new_body
        assert before['user']['username'] == 'alexar76'
        if before['ai_disclosure_level'] != 'not_disclosed' or before['body_markdown'] != new_body:
            assert digest(before['body_markdown']) == change['oldBodySha256'], 'Concurrent article edit'
            api.request(f"/api/articles/{change['id']}", 'PUT', {'article': {
                'ai_disclosure_level': 'not_disclosed', 'body_markdown': new_body}})
        public = api.request('/api/articles' + before['path'] + '?badge_check=' + str(int(datetime.now().timestamp())), authenticated=False)
        assert public['user']['username'] == 'alexar76' and public['published_at']
        assert public['ai_disclosure_level'] == 'not_disclosed' and public['body_markdown'] == new_body
        (FOLDER / f"{change['topic']}.verified.json").write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
        result.append({**change, 'verifiedAt': datetime.now(timezone.utc).isoformat(), 'verified': True})
    protected_after = api.get_article(4914122)
    assert protected_after['ai_disclosure_level'] == 'fully_autonomous'
    assert protected_after['body_markdown'] == protected_before['body_markdown']
    (FOLDER / 'result.json').write_text(json.dumps({'changes': result, 'jkmingUnchanged': True}, indent=2) + '\n')
    for state_name in ('devto-state.json', 'status.json'):
        path = ROOT / state_name
        state = json.loads(path.read_text())
        for change in result:
            entry = state['articles'].setdefault(change['topic'], {'id': change['id'], 'url': change['url']})
            entry.update({'bodySha256': change['newBodySha256'], 'aiDisclosureLevelRequested': 'not_disclosed',
                          'aiDisclosureLevelVerified': 'not_disclosed', 'verifiedAt': change['verifiedAt']})
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    for topic in TOPICS:
        for filename in ('article.md', 'article.published.md'):
            path = ROOT / topic / filename
            if path.exists():
                path.write_text(path.read_text().replace(HEADER, NEW_HEADER, 1))
    print(json.dumps({'updated': [c['topic'] for c in result], 'publiclyVerified': True,
                      'detailedAiDisclosureRetained': True, 'jkmingUnchanged': True}, indent=2))


if __name__ == '__main__':
    main()
