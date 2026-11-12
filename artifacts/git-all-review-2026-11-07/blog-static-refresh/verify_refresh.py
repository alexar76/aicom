"""Extend the existing full-build proof with current post attachment checks."""
import json
from pathlib import Path
import runpy


state = runpy.run_path('/original-scripts/verify_static.py')
report = state['report']
blog, dist, sha = state['blog'], state['dist'], state['sha']
attachments = []
for slug in state['POSTS']:
    meta = json.loads((blog / 'posts' / slug / 'meta.json').read_text())
    revision = meta['image_revision']
    assert revision and meta['cover_file'] == 'cover-v2.png'
    for name in meta.get('public_files', []):
        source = blog / 'posts' / slug / name
        target = dist / slug / name
        assert sha(source) == sha(target), f'Current post attachment mismatch: {slug}/{name}'
        attachments.append({'post': slug, 'path': name, 'sha256': sha(source)})
    for name in ('cover.webp', 'card.webp', 'og.jpg'):
        suffix = Path(name).suffix
        revised = f'{Path(name).stem}-{revision}{suffix}'
        assert (dist / slug / revised).is_file(), f'Current image revision missing: {slug}/{revised}'
report['current_post_attachments'] = attachments
report['post_image_revisions_verified'] = len(state['POSTS'])
(state['RESULTS'] / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'current_post_attachments_verified': len(attachments), 'post_image_revisions_verified': len(state['POSTS'])}))
