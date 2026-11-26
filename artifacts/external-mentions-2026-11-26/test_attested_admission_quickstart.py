"""Check the published signup example through local services with admission enabled."""

import hashlib
import html
import importlib.util
from pathlib import Path
import re
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_PROBE = ROOT / "artifacts/external-mentions-2026-11-25/implementation/test_attested_quickstart.py"
PUBLISHED_EXAMPLE_SHA256 = "a30d6a38af6b75c265d65a5c49c39e487342c3056d041614d968befc52906117"
spec = importlib.util.spec_from_file_location("previous_attested_probe", PREVIOUS_PROBE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
ecosystem = probe.ecosystem


def test_published_example_with_explicit_operator_approval(ecosystem, monkeypatch, capsys):
    _, market, clients, personal, _, _ = ecosystem
    monkeypatch.setattr(
        urllib.request, "build_opener",
        lambda *_: probe.proxy_test._Edge(clients["gateway.review"], personal),
    )
    page = (ROOT / "saas-landing/developers.html").read_text()
    match = re.search(r'<pre[^>]+id="share-revoke-example">(.*?)</pre>', page, re.DOTALL)
    assert match is not None
    example = html.unescape(match[1]).strip()
    assert hashlib.sha256(example.encode()).hexdigest() == PUBLISHED_EXAMPLE_SHA256
    before_share, separator, after_share = example.partition("owner.share(")
    assert separator
    scope = {}
    exec(compile(before_share, "<published example through write>", "exec"), scope)
    memory_id = scope["memory_id"]
    assert market.get_unchecked(memory_id).review_state == "pending"

    rest = compile(separator + after_share, "<published share and revoke>", "exec")
    with pytest.raises(scope["AttestedMemoryError"]) as failure:
        exec(rest, scope)
    assert failure.value.status == 404

    assert market.review(memory_id, "approved", "operator:fixture").review_state == "approved"
    exec(rest, scope)
    assert capsys.readouterr().out.strip() == "Access revoked (HTTP 403)"
