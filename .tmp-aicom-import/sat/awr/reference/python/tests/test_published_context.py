"""The JSON-LD context that gets deployed must be the one in the repository.

`awr/ns/v2/context.json` is the source of truth; `docs/verifier/ns/awr/v2.jsonld` is the
copy the rsync in deploy/nginx/verify.modelmarket.dev.conf actually publishes. Two copies
of the same document that drift apart is the failure this whole project exists because of,
so it is a test rather than a convention.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SOURCE = REPO / "awr" / "ns" / "v2" / "context.json"
PUBLISHED = REPO / "docs" / "verifier" / "ns" / "awr" / "v2.jsonld"


def test_the_published_context_matches_the_source():
    assert SOURCE.exists(), SOURCE
    assert PUBLISHED.exists(), (
        "%s is missing: the namespace URI would fall through to the verifier's SPA "
        "fallback and answer a context request with text/html" % (PUBLISHED,)
    )
    assert SOURCE.read_bytes() == PUBLISHED.read_bytes()


def test_the_context_declares_the_namespace_it_is_served_at():
    ctx = json.loads(SOURCE.read_text())["@context"]
    assert ctx["awr"].startswith("https://verify.modelmarket.dev/ns/awr/v2")


def test_it_does_not_redefine_a_vc2_protected_term():
    """Redefining one makes expansion fail outright rather than degrade."""
    ctx = json.loads(SOURCE.read_text())["@context"]
    terms = set()

    def walk(node):
        for key, value in node.items():
            if key.startswith("@"):
                continue
            terms.add(key)
            if isinstance(value, dict) and "@context" in value:
                walk(value["@context"])

    walk(ctx)
    # The five found by diffing against the VC 2.0 context, three of them only after
    # expansion failed on 12 of 15 valid vectors.
    assert not (terms & {"digestSRI", "evidence", "status", "nonce", "name"})
