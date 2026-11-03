"""Runs inside the new image with no network: the MTL/1.1 files are the ones built, and they digest as tested."""
import hashlib, inspect, json, sys

expected = dict(reversed(line.split()) for line in open("/ctx/expected.sha256") if line.strip())
for rel, digest in expected.items():
    path = "/app/" + rel
    got = hashlib.sha256(open(path, "rb").read()).hexdigest()
    assert got == digest, (rel, got, digest)
import histor.app, histor.crawler, histor.dataset  # noqa: E401,F401 - the whole app imports
from histor.labels import LabelIssuer
from histor.subject import MtlError, build_subject, es_number, tool_set_digest
from histor.store import Store

v = json.load(open("/ctx/mtl-vectors.json"))
for name in ("basic", "output", "unicode", "fraction", "exponent", "largeInteger", "empty", "duplicate"):
    assert tool_set_digest(v[name]["tools"])[0] == v[name]["digest"], name
assert es_number(1e21) == "1e+21" and es_number(0.7) == "0.7" and es_number(5.0) == "5"
s = build_subject(server_name="s", registry="r", tools=[{"name": "p", "inputSchema": {"maximum": float("inf")}}])
assert s.hazard is not None and s.hazard.code == "MTL-NUM-001" and s.tool_set_digest is None
try:
    tool_set_digest([{"description": "no name"}])
    raise SystemExit("a nameless entry was digested")
except MtlError as exc:
    assert exc.code == "MTL-SUBJ-001"
assert "prior_no_digest_code" in inspect.signature(LabelIssuer.continuity).parameters
assert "undigested" in inspect.getsource(Store.search_targets)
assert hasattr(histor.crawler.Crawler, "_only_gains_digest") and hasattr(histor.crawler.Crawler, "_no_digest_reason")
print(f"smoke ok: {len(expected)} files as built, 8 vectors, NUM-001 only for 1e400, SUBJ-001 for a nameless entry")
