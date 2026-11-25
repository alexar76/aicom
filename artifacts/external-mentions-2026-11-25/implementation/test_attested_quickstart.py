"""Run the published Python wheel against the exact HTML quickstart and local services."""
import hashlib
import html
import importlib.util
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WHEEL = ROOT / ('artifacts/attested-memory-0.3.0-release-2026-11-25/wheels/'
                'attested_memory-0.3.0-py3-none-any.whl')
WHEEL_SHA256 = 'fabb127ec024d3ab978ae5a244a53804f156beacd04d3bba90ded811cd0eb6b1'
assert hashlib.sha256(WHEEL.read_bytes()).hexdigest() == WHEEL_SHA256
sys.path.insert(0, str(WHEEL))
import attested_memory

# Load the wheel first. The existing integration fixture also adds the SDK source path.
assert Path(attested_memory.__file__).is_relative_to(WHEEL)
spec = importlib.util.spec_from_file_location(
    'actor_proxy_test', ROOT / 'attested/tests/test_actor_proxy_flow.py',
)
proxy_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy_test)
ecosystem = proxy_test.ecosystem


def test_share_revoke_from_developers_page(ecosystem, monkeypatch, capsys):
    _, _, clients, personal, _, _ = ecosystem
    monkeypatch.setattr(urllib.request, 'build_opener',
                        lambda *_: proxy_test._Edge(clients['gateway.review'], personal))
    page = (ROOT / 'saas-landing/developers.html').read_text()
    assert 'python -m pip install attested-memory==0.3.0' in page
    snippet = re.search(r'<pre[^>]+id="share-revoke-example">(.*?)</pre>', page, re.DOTALL)
    assert snippet is not None
    exec(compile(html.unescape(snippet[1]), '<developers share and revoke>', 'exec'), {})
    assert capsys.readouterr().out.strip() == 'Access revoked (HTTP 403)'
