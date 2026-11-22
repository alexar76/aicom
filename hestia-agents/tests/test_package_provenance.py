"""package.provenance.verify@v1 against npm and PyPI releases as they stood on 2026-11-21.

`package_provenance_vectors.json` holds what registry.npmjs.org and pypi.org answered on 2026-11-21
(scripts/record_fetches.py, the hearth's limits applied) for eight calls: @modelcontextprotocol/sdk
1.32.2 (Sigstore bundle v0.3, Rekor dsse 0.0.1), sigstore 3.0.0 on npm (bundle v0.2, intoto 0.0.2,
signed by npm's key that expired 2025-01-29, before it expired), @aimarket/warden 0.35.0 and
aimarket-histor 0.10.0 (no provenance), sigstore 4.5.1 and mcp 2.3.0 on PyPI (PEP 740), the SDK
with a wrong expected repository, and a package that does not exist.

Every cryptographic check is shown to fail on its own when one recorded byte changes: the DSSE
signature, the payload, the Rekor SET, the inclusion path, the checkpoint signature, the
certificate, the tarball digest, npm's key list and PyPI's trusted publisher.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import pytest
from replay import load, text_of, with_json

from hestia_agents.manifests import AGENTS, deploy_body

V = json.loads(
    (Path(__file__).parent / "package_provenance_vectors.json").read_text(encoding="utf-8")
)
SLUG = "package-provenance"


def run(case, tamper=None, payload=None):
    handle, asked, ns = load(SLUG, V[case]["fetched"], tamper)
    return handle(payload or V[case]["payload"]), asked, ns


def failing(out):
    rows = out.get("attestations") or [
        a for f in out.get("files", []) for a in f.get("attestations") or []
    ]
    return sorted({c["check"] for a in rows for c in a.get("checks", []) if not c["ok"]})


def slsa(out):
    return next(
        a for a in out["attestations"] if a["predicate_type"] == "https://slsa.dev/provenance/v1"
    )


def npm_attestations(change):
    """A tamper that edits the SLSA bundle of the npm attestations reply."""

    def tamper(url, raw):
        if "/-/npm/v1/attestations/" in url:
            doc = text_of(raw)
            bundle = next(a for a in doc["attestations"] if "slsa" in a["predicateType"])["bundle"]
            change(bundle)
            return with_json(raw, doc)
        return raw

    return tamper


def flip(b64, at=10):
    raw = bytearray(base64.b64decode(b64))
    raw[at] ^= 1
    return base64.b64encode(bytes(raw)).decode()


# ------------------------------------------------------------------ recorded, unchanged


def test_the_mcp_sdk_on_npm_verifies_end_to_end_and_names_its_build() -> None:
    out, asked, _ = run("sdk")
    assert out["verdict"] == "verified" and failing(out) == []
    assert [c["check"] for c in slsa(out)["checks"]] == [
        "dsse_signature",
        "rekor_log",
        "rekor_set",
        "rekor_inclusion",
        "rekor_checkpoint",
        "rekor_body",
        "certificate_chain",
        "code_signing",
        "certificate_valid_when_logged",
        "subject",
        "expected_repository",
        "expected_workflow",
        "expected_ref",
    ]
    assert out["built_from"] == {
        "repository": "https://github.com/modelcontextprotocol/typescript-sdk",
        "commit": "3b73021a0a2272c0c04c3917bcdb03398b3ec63f",
        "ref": "refs/tags/1.32.2",
        "workflow": "https://github.com/modelcontextprotocol/typescript-sdk/.github/workflows/main.yml",
        "trigger": "release",
        "runner": "github-hosted",
        "run": "https://github.com/modelcontextprotocol/typescript-sdk/actions/runs/40000576535/attempts/1",
        "issuer": "https://token.actions.githubusercontent.com",
    }
    assert [s["ok"] for s in out["registry_signatures"]] == [True, True]
    assert slsa(out)["logged_at"] == "2026-10-23T18:08:51Z"
    assert asked == [
        "https://registry.npmjs.org/@modelcontextprotocol%2Fsdk/1.32.2",
        "https://registry.npmjs.org/-/npm/v1/keys",
        "https://registry.npmjs.org/-/npm/v1/attestations/@modelcontextprotocol%2Fsdk@1.32.2",
    ]


def test_an_older_bundle_with_intoto_entries_and_a_since_expired_npm_key_verifies() -> None:
    out, _, _ = run("sigstore_js_old")
    assert out["verdict"] == "verified" and failing(out) == []
    kinds = {a["predicate_type"]: a["bundle"] for a in out["attestations"]}
    assert set(kinds.values()) == {"application/vnd.dev.sigstore.bundle+json;version=0.2"}
    assert out["built_from"]["repository"] == "https://github.com/sigstore/sigstore-js"


def test_a_release_without_attestations_is_no_provenance_but_its_registry_signatures_are_checked() -> (
    None
):
    out, asked, _ = run("warden_none")
    assert out["verdict"] == "no_provenance" and len(asked) == 2
    assert [s["ok"] for s in out["registry_signatures"]] == [True, True]


def test_pypi_files_verify_with_their_trusted_publisher() -> None:
    out, asked, _ = run("pypi_sigstore")
    assert out["verdict"] == "verified" and failing(out) == []
    assert [f["filename"] for f in out["files"]] == [
        "sigstore-4.5.1-py3-none-any.whl",
        "sigstore-4.5.1.tar.gz",
    ]
    for f in out["files"]:
        (att,) = f["attestations"]
        assert att["publisher"] == {
            "environment": None,
            "kind": "GitHub",
            "repository": "sigstore/sigstore-python",
            "workflow": "release.yml",
        }
        assert "trusted_publisher" in [c["check"] for c in att["checks"]]
    assert out["built_from"]["ref"] == "refs/tags/v4.5.1"
    out, _, _ = run("pypi_mcp")
    assert out["verdict"] == "verified"
    assert (
        out["built_from"]["workflow"]
        == "https://github.com/modelcontextprotocol/python-sdk/.github/workflows/publish-pypi.yml"
    )


def test_a_pypi_release_without_attestations_names_its_files() -> None:
    out, _, _ = run("pypi_histor_none")
    assert out["verdict"] == "no_provenance"
    assert out["files_without_provenance"] == [
        "aimarket_histor-0.10.0-py3-none-any.whl",
        "aimarket_histor-0.10.0.tar.gz",
    ]


def test_another_expected_repository_is_an_expectation_mismatch_not_invalid() -> None:
    out, _, _ = run("sdk_wrong_repo")
    assert out["verdict"] == "expectation_mismatch" and failing(out) == ["expected_repository"]


def test_an_unknown_package_is_not_found() -> None:
    out, asked, _ = run("npm_missing")
    assert out["verdict"] == "not_found" and len(asked) == 1


# ------------------------------------------------------------------ one changed byte each


def test_a_changed_signature_fails_dsse_and_the_logged_body() -> None:
    def change(bundle):
        sig = bundle["dsseEnvelope"]["signatures"][0]
        sig["sig"] = flip(sig["sig"], 20)

    out, _, _ = run("sdk", npm_attestations(change))
    assert out["verdict"] == "invalid"
    assert {"dsse_signature", "rekor_body"} <= set(failing(out))


def test_a_changed_statement_fails_the_signature_the_log_and_the_subject() -> None:
    def change(bundle):
        statement = json.loads(base64.b64decode(bundle["dsseEnvelope"]["payload"]))
        statement["subject"][0]["digest"]["sha512"] = "00" * 64
        bundle["dsseEnvelope"]["payload"] = base64.b64encode(
            json.dumps(statement).encode()
        ).decode()

    out, _, _ = run("sdk", npm_attestations(change))
    assert out["verdict"] == "invalid"
    assert {"dsse_signature", "rekor_body", "subject"} <= set(failing(out))


def test_a_changed_signed_entry_timestamp_fails_the_set_only() -> None:
    def change(bundle):
        promise = bundle["verificationMaterial"]["tlogEntries"][0]["inclusionPromise"]
        promise["signedEntryTimestamp"] = flip(promise["signedEntryTimestamp"], 30)

    out, _, _ = run("sdk", npm_attestations(change))
    assert failing(out) == ["rekor_set"] and out["verdict"] == "invalid"


def test_a_changed_inclusion_path_fails_the_inclusion_only() -> None:
    def change(bundle):
        hashes = bundle["verificationMaterial"]["tlogEntries"][0]["inclusionProof"]["hashes"]
        hashes[3] = flip(hashes[3], 0)

    out, _, _ = run("sdk", npm_attestations(change))
    assert failing(out) == ["rekor_inclusion"]


def test_a_changed_checkpoint_signature_fails_the_checkpoint_only() -> None:
    def change(bundle):
        cp = bundle["verificationMaterial"]["tlogEntries"][0]["inclusionProof"]["checkpoint"]
        body, sig_line = cp["envelope"].rstrip("\n").rsplit("\n", 1)
        name, b64 = sig_line.rsplit(" ", 1)
        cp["envelope"] = body + "\n" + name + " " + flip(b64, 40) + "\n"

    out, _, _ = run("sdk", npm_attestations(change))
    assert failing(out) == ["rekor_checkpoint"]


def test_a_changed_certificate_fails_its_chain_and_the_logged_key() -> None:
    def change(bundle):
        cert = bundle["verificationMaterial"]["certificate"]
        raw = bytearray(base64.b64decode(cert["rawBytes"]))
        raw[400] ^= 1  # inside the extensions of tbsCertificate
        cert["rawBytes"] = base64.b64encode(bytes(raw)).decode()

    out, _, _ = run("sdk", npm_attestations(change))
    assert "certificate_chain" in failing(out) and "rekor_body" in failing(out)


def test_a_different_tarball_digest_fails_the_subjects_and_the_registry_signatures() -> None:
    def tamper(url, raw):
        if url.endswith("/@modelcontextprotocol%2Fsdk/1.32.2"):
            doc = text_of(raw)
            doc["dist"]["integrity"] = "sha512-" + base64.b64encode(b"\x11" * 64).decode()
            return with_json(raw, doc)
        return raw

    out, _, _ = run("sdk", tamper)
    assert out["verdict"] == "invalid" and failing(out) == ["subject"]
    assert [s["ok"] for s in out["registry_signatures"]] == [False, False]


def test_a_listed_npm_key_whose_id_is_not_its_fingerprint_is_not_used() -> None:
    def tamper(url, raw):
        if url.endswith("/-/npm/v1/keys"):
            doc = text_of(raw)
            for k in doc["keys"]:
                k["keyid"], k["key"] = (
                    k["keyid"],
                    doc["keys"][0]["key"],
                )  # every id now names the old key's bytes
            return with_json(raw, doc)
        return raw

    out, _, _ = run("sdk", tamper)
    assert out["verdict"] == "invalid"
    publish = next(a for a in out["attestations"] if "npm/attestation" in a["predicate_type"])
    assert (
        publish["checks"][0]["check"] == "readable"
        and "does not list" in publish["checks"][0]["detail"]
    )


def test_a_signature_logged_after_its_npm_key_expired_fails() -> None:
    def tamper(url, raw):
        if url.endswith("/-/npm/v1/keys"):
            doc = text_of(raw)
            for k in doc["keys"]:
                k["expires"] = "2026-01-01T00:00:00.000Z"
            return with_json(raw, doc)
        return raw

    out, _, _ = run("sdk", tamper)
    assert "key_not_expired" in failing(out)


def test_a_trusted_publisher_that_is_not_the_certificates_repository_fails() -> None:
    def tamper(url, raw):
        if "/integrity/" in url:
            doc = text_of(raw)
            doc["attestation_bundles"][0]["publisher"]["repository"] = "someone/sigstore-python"
            return with_json(raw, doc)
        return raw

    out, _, _ = run("pypi_sigstore", tamper)
    assert out["verdict"] == "invalid" and failing(out) == ["trusted_publisher"]


def test_a_pinned_file_is_the_only_one_asked() -> None:
    payload = dict(V["pypi_sigstore"]["payload"], file="sigstore-4.5.1.tar.gz")
    out, asked, _ = run("pypi_sigstore", payload=payload)
    assert [f["filename"] for f in out["files"]] == ["sigstore-4.5.1.tar.gz"] and len(asked) == 2


# ------------------------------------------------------------------ pieces


def test_the_certificate_window_is_judged_at_the_logged_time() -> None:
    _, _, ns = run("sdk")
    bundle = next(
        a
        for a in text_of(next(v for k, v in V["sdk"]["fetched"].items() if "attestations/" in k))[
            "attestations"
        ]
        if "slsa" in a["predicateType"]
    )["bundle"]
    leaf = ns["parse_cert"](
        base64.b64decode(bundle["verificationMaterial"]["certificate"]["rawBytes"])
    )
    assert leaf["not_after"] - leaf["not_before"] == 600  # Fulcio issues ten-minute certificates
    checks = []
    ns["_chain"](checks, leaf, leaf["not_after"] + 1)
    assert [(c["check"], c["ok"]) for c in checks] == [
        ("certificate_chain", True),
        ("code_signing", True),
        ("certificate_valid_when_logged", False),
    ]
    assert leaf["fulcio"]["source_repository_digest"] == "3b73021a0a2272c0c04c3917bcdb03398b3ec63f"
    assert leaf["fulcio"]["issuer_v1"] == "https://token.actions.githubusercontent.com"


def test_npm_key_ids_are_openssh_fingerprints() -> None:
    _, _, ns = run("sdk")
    keys = text_of(next(v for k, v in V["sdk"]["fetched"].items() if k.find("/-/npm/v1/keys") > 0))[
        "keys"
    ]
    for k in keys:
        assert ns["ssh_fingerprint"](ns["spki_key"](base64.b64decode(k["key"]))) == k["keyid"]


def test_time_conversions_agree() -> None:
    _, _, ns = run("sdk")
    for stamp in (
        "1970-01-01T00:00:00Z",
        "2000-02-29T12:34:56Z",
        "2026-10-23T18:08:51Z",
        "2099-12-31T23:59:59Z",
    ):
        assert ns["_iso"](ns["_stamp"](stamp)) == stamp


def test_pae_is_dsse_v1() -> None:
    _, _, ns = run("sdk")
    assert (
        ns["pae"]("application/vnd.in-toto+json", b"{}")
        == b"DSSEv1 28 application/vnd.in-toto+json 2 {}"
    )


def test_the_pinned_trust_root_is_sigstores() -> None:
    _, _, ns = run("sdk")
    cas = ns["CAS"]
    assert [ca["from"] for ca in cas] == ["2021-03-07T03:20:29Z", "2022-04-13T20:06:15Z"]
    assert cas[1]["chain"][0]["subject"] != cas[1]["chain"][1]["subject"]  # intermediate, then root
    assert ns["REKOR_LOG_ID"] == "wNI9atQGlz+VWfO6LRygH4QUfY/8W4RFwiT5i5WRgB0="
    root = cas[1]["chain"][1]
    intermediate = cas[1]["chain"][0]
    assert ns["ecdsa_verify"](
        root["key"], intermediate["sig_hash"], intermediate["tbs"], intermediate["signature"]
    )


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"package": "x"}, "ecosystem"),
        ({"ecosystem": "cargo", "package": "x"}, "ecosystem"),
        ({"ecosystem": "npm"}, "package"),
        ({"ecosystem": "npm", "package": "@scope"}, "scoped"),
        ({"ecosystem": "pypi", "package": "a/b"}, "slash"),
        ({"ecosystem": "npm", "package": "x", "file": "x.whl"}, "file"),
        ({"ecosystem": "npm", "package": "x", "version": "1 2"}, "version"),
    ],
)
def test_bad_input_is_refused_before_any_fetch(payload, message) -> None:
    handle, asked, _ = load(SLUG, {})
    with pytest.raises(ValueError, match=message):
        handle(payload)
    assert asked == []


def test_manifest_reaches_only_the_two_registries_and_is_free() -> None:
    meta = AGENTS[SLUG]
    assert (
        meta["capability_id"] == "package.provenance.verify@v1" and meta["price_per_call_usd"] == 0
    )
    body = deploy_body(SLUG)
    assert (
        body["egress_hosts"] == ["registry.npmjs.org", "pypi.org"]
        and "egress_input_fields" not in body
    )
    assert copy.deepcopy(meta["probe"]) == {
        "ecosystem": "npm",
        "package": "@modelcontextprotocol/sdk",
        "version": "1.32.2",
    }
