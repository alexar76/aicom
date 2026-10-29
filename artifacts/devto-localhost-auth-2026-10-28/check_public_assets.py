"""Exercise the actual blog asset copier without optional rendering dependencies."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[2]
tree = ast.parse((ROOT / 'modelmarket-blog/build.py').read_text())
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'copy_public_assets')
namespace = {'Path':Path, 'json':json, 'hashlib':hashlib, 'shutil':shutil,
             'HERE':ROOT/'modelmarket-blog'}
exec(compile(ast.Module(body=[node], type_ignores=[]), 'modelmarket-blog/build.py', 'exec'), namespace)
destination = Path('/private/tmp/devto-localhost-assets-verified')
destination.mkdir(exist_ok=True)
count = namespace['copy_public_assets'](destination)
assert count == 6
checks = ['six_registered_real_images_copied_with_matching_hashes']

with tempfile.TemporaryDirectory() as temp:
    base = Path(temp)
    here = base/'aicompany/aicom/modelmarket-blog'
    promo = base/'aicompany/PromoMaterials'
    here.mkdir(parents=True);promo.mkdir(parents=True)
    source = promo/'image.png';source.write_bytes(b'fixed test image bytes')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    namespace['HERE'] = here
    def manifest(entry, files=None):
        (here/'public-assets.json').write_text(json.dumps({'schema':'modelmarket-blog-public-assets/1', 'files':files or {}, 'promo_files':{'media/test/image.png':entry}}))
    def rejected(label):
        try:namespace['copy_public_assets'](base/'out')
        except ValueError:checks.append(label)
        else:raise AssertionError(label)
    manifest({'source':'image.png','sha256':digest})
    assert namespace['copy_public_assets'](base/'out') == 1
    checks.append('canonical_promotional_source_accepted')
    manifest({'source':'../outside.png','sha256':digest});rejected('parent_traversal_rejected')
    manifest({'source':'image.png','sha256':'wrong'});rejected('tampered_source_rejected')
    outside = base/'outside.png';outside.write_bytes(source.read_bytes())
    (promo/'link.png').symlink_to(outside)
    manifest({'source':'link.png','sha256':digest});rejected('external_symlink_rejected')
    manifest({'source':'image.png','sha256':digest},{'media/test/image.png':digest})
    rejected('duplicate_destination_rejected')

(Path(__file__).parent/'public-assets-validation.json').write_text(json.dumps({'passed':True,'checks':checks,'staged_images':count},indent=2)+'\n')
print(json.dumps({'passed':True,'checks':len(checks),'staged_images':count}))
