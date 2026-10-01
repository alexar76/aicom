"""The section 17 CLI contract."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys

import pytest
from conftest import (
    CREATED,
    NOW,
    VALID_FROM,
    make_receipt,
    make_verdict,
    record_code,
    work_receipt_subject,
)

from awr.cli import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_UNIMPLEMENTED,
    EXIT_USAGE,
    main,
)
from awr.jcs import canonicalize
from awr.proof import hash_data_for_document
from awr.verify import make_bundle, verify_document

PYTHON = sys.executable
PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(argv):
    """Run the CLI in-process, capturing stdout and stderr separately."""
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, out, err)
    return code, out.getvalue(), err.getvalue()


def write(tmp_path, name, value):
    path = tmp_path / name
    if isinstance(value, (bytes, bytearray)):
        path.write_bytes(value)
    else:
        path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def test_verify_valid_document_exits_zero(tmp_path, key_a):
    path = write(tmp_path, "receipt.awr.json", make_receipt(key_a))
    code, out, err = run(["verify", path, "--now", NOW])
    assert code == EXIT_OK
    result = json.loads(out)
    assert result["valid"] is True
    assert result["documentType"] == "WorkReceipt"
    assert result["profile"] == "L0"
    assert err == ""


def test_verify_invalid_document_exits_one_and_still_prints_a_result(tmp_path, key_a):
    receipt = make_receipt(key_a)
    receipt["credentialSubject"]["work"]["status"] = "nope"
    path = write(tmp_path, "broken.awr.json", receipt)
    code, out, err = run(["verify", path, "--now", NOW])
    assert code == EXIT_INVALID
    result = json.loads(out)
    assert result["valid"] is False
    codes = [entry["code"] for entry in result["reasons"]]
    assert "AWR-RCPT-006" in codes
    assert "AWR-PROOF-006" in codes
    # Diagnostics on stderr, payload on stdout.
    assert "AWR-RCPT-006" in err
    for code_name in ("AWR-RCPT-006", "AWR-PROOF-006"):
        record_code(code_name)


def test_verify_result_has_the_section_11_1_shape(tmp_path, key_a):
    path = write(tmp_path, "receipt.awr.json", make_receipt(key_a))
    _, out, _ = run(["verify", path, "--now", NOW])
    result = json.loads(out)
    for member in (
        "valid",
        "awrVersion",
        "documentType",
        "profile",
        "reasons",
        "warnings",
        "chain",
    ):
        assert member in result, member
    assert set(result["chain"]) == {"resolved", "unresolved"}
    assert isinstance(result["reasons"], list)
    assert isinstance(result["warnings"], list)


def test_verify_profile_l1_with_parents_flag(tmp_path, key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = make_verdict(key_b, receipt)
    receipt_path = write(tmp_path, "receipt.awr.json", receipt)
    verdict_path = write(tmp_path, "verdict.awr.json", verdict)

    code, out, _ = run(
        ["verify", receipt_path, "--profile", "L1", "--parents", verdict_path, "--now", NOW]
    )
    assert code == EXIT_OK
    assert json.loads(out)["profile"] == "L1"

    code, out, err = run(["verify", receipt_path, "--profile", "L1", "--now", NOW])
    assert code == EXIT_INVALID
    assert "AWR-PROFILE-001" in [e["code"] for e in json.loads(out)["reasons"]]
    assert "AWR-PROFILE-001" in err


def test_verify_accepts_a_bundle(tmp_path, key_a, key_b):
    receipt = make_receipt(key_a)
    verdict = make_verdict(key_b, receipt)
    path = write(tmp_path, "b.awrb.json", make_bundle([receipt, verdict]))
    code, out, _ = run(["verify", path, "--profile", "L1", "--now", NOW])
    assert code == EXIT_OK
    result = json.loads(out)
    assert result["profile"] == "L1"
    assert result["subjectId"] == receipt["id"]


def test_verify_parents_may_be_a_bundle(tmp_path, key_a):
    from awr.documents import document_reference
    from conftest import build_unsecured, sign

    parent = make_receipt(key_a)
    child = sign(
        build_unsecured(
            key_a, subject=work_receipt_subject(parents=[document_reference(parent)])
        ),
        key_a,
    )
    child_path = write(tmp_path, "child.awr.json", child)
    parents_path = write(tmp_path, "parents.awrb.json", make_bundle([parent]))
    code, out, _ = run(["verify", child_path, "--parents", parents_path, "--now", NOW])
    assert code == EXIT_OK
    assert json.loads(out)["chain"] == {"resolved": 1, "unresolved": 0}


def test_verify_now_makes_the_time_warnings_deterministic(tmp_path, key_a):
    from conftest import build_unsecured, sign

    receipt = sign(
        build_unsecured(key_a, overrides={"validFrom": "2030-01-01T00:00:00Z"}),
        key_a,
        created="2030-01-01T00:00:00Z",
    )
    path = write(tmp_path, "future.awr.json", receipt)

    code, out, _ = run(["verify", path, "--now", "2026-07-31T12:00:00Z"])
    assert code == EXIT_OK
    assert "AWR-TIME-001" in [w["code"] for w in json.loads(out)["warnings"]]

    code, out, _ = run(["verify", path, "--now", "2031-01-01T00:00:00Z"])
    assert code == EXIT_OK
    assert json.loads(out)["warnings"] == []
    record_code("AWR-TIME-001")


def test_verify_rejects_a_malformed_now(tmp_path, key_a):
    path = write(tmp_path, "receipt.awr.json", make_receipt(key_a))
    code, out, err = run(["verify", path, "--now", "yesterday"])
    assert code == EXIT_USAGE
    assert out == ""
    assert "--now" in err


def test_verify_chain_limits_are_configurable_from_the_cli(tmp_path, key_a):
    from test_chain import linear_chain

    documents = linear_chain(key_a, 5)
    subject_path = write(tmp_path, "terminal.awr.json", documents[-1])
    parents_path = write(tmp_path, "parents.awrb.json", make_bundle(documents[:-1]))
    code, out, _ = run(
        [
            "verify",
            subject_path,
            "--parents",
            parents_path,
            "--max-depth",
            "2",
            "--now",
            NOW,
        ]
    )
    assert code == EXIT_INVALID
    assert "AWR-CHAIN-005" in [e["code"] for e in json.loads(out)["reasons"]]
    record_code("AWR-CHAIN-005")


# ---------------------------------------------------------------------------
# canonicalize
# ---------------------------------------------------------------------------


def test_canonicalize_prints_the_canonical_bytes_with_no_trailing_newline(tmp_path):
    value = {"b": 1, "a": [True, None, "x"], "\U0001f600": "astral"}
    path = write(tmp_path, "value.json", value)
    code, out, err = run(["canonicalize", path])
    assert code == EXIT_OK
    assert out == canonicalize(value).decode("utf-8")
    assert not out.endswith("\n")
    assert err == ""


def test_canonicalize_reports_a_canonicalization_failure_on_stderr(tmp_path):
    path = write(tmp_path, "float.json", b'{"n": 1.5}')
    code, out, err = run(["canonicalize", path])
    assert code == EXIT_INVALID
    assert out == ""
    assert "AWR-CANON-001" in err
    record_code("AWR-CANON-001")


def test_canonicalize_reports_duplicate_keys(tmp_path):
    path = write(tmp_path, "dup.json", b'{"a":1,"a":2}')
    code, out, err = run(["canonicalize", path])
    assert code == EXIT_INVALID
    assert "AWR-CANON-004" in err
    record_code("AWR-CANON-004")


# ---------------------------------------------------------------------------
# digest
# ---------------------------------------------------------------------------


def test_digest_prints_an_sri_string_over_the_canonical_bytes(tmp_path, key_a):
    from awr.digest import canonical_sri

    receipt = make_receipt(key_a)
    path = write(tmp_path, "receipt.awr.json", receipt)
    code, out, err = run(["digest", path])
    assert code == EXIT_OK
    assert out.strip() == canonical_sri(receipt)
    assert out.startswith("sha256-")
    assert err == ""


def test_digest_of_an_empty_object_is_reproducible(tmp_path):
    path = write(tmp_path, "empty.json", {})
    code, out, _ = run(["digest", path])
    assert code == EXIT_OK
    # sha256 of the two bytes "{}"
    import hashlib
    import base64

    expected = "sha256-" + base64.b64encode(hashlib.sha256(b"{}").digest()).decode()
    assert out.strip() == expected


# ---------------------------------------------------------------------------
# hashdata
# ---------------------------------------------------------------------------


def test_hashdata_prints_the_three_values_as_hex_one_per_line(tmp_path, key_a):
    receipt = make_receipt(key_a)
    path = write(tmp_path, "receipt.awr.json", receipt)
    code, out, err = run(["hashdata", path])
    assert code == EXIT_OK
    assert err == ""
    lines = out.strip().split("\n")
    assert len(lines) == 3
    proof_config_hash, transformed_hash, hash_data = (bytes.fromhex(line) for line in lines)
    assert (proof_config_hash, transformed_hash, hash_data) == hash_data_for_document(receipt)
    assert lines[2] == lines[0] + lines[1]
    assert len(lines[0]) == len(lines[1]) == 64
    assert len(lines[2]) == 128


def test_hashdata_needs_a_proof_object(tmp_path, key_a):
    from conftest import build_unsecured

    path = write(tmp_path, "unsecured.json", build_unsecured(key_a))
    code, out, err = run(["hashdata", path])
    assert code == EXIT_USAGE
    assert out == ""
    assert "proof" in err


# ---------------------------------------------------------------------------
# issue
# ---------------------------------------------------------------------------


def key_file(tmp_path, key, name="key.json"):
    path = tmp_path / name
    path.write_text(json.dumps(key.private_key_jwk()), encoding="utf-8")
    return str(path)


def test_issue_produces_a_document_that_verifies(tmp_path, key_a):
    subject_path = write(tmp_path, "subject.json", work_receipt_subject())
    code, out, err = run(
        [
            "issue",
            subject_path,
            "--key",
            key_file(tmp_path, key_a),
            "--id",
            "urn:uuid:issued-1",
            "--now",
            VALID_FROM,
        ]
    )
    assert code == EXIT_OK
    document = json.loads(out)
    assert document["id"] == "urn:uuid:issued-1"
    assert document["issuer"]["id"] == key_a.did
    assert document["validFrom"] == VALID_FROM
    assert document["proof"]["cryptosuite"] == "eddsa-jcs-2022"
    assert verify_document(document, now=NOW)["valid"] is True
    assert key_a.did in err  # the diagnostic, on stderr


def test_issue_is_byte_identical_for_a_fixed_id_and_now(tmp_path, key_a):
    subject_path = write(tmp_path, "subject.json", work_receipt_subject())
    argv = [
        "issue",
        subject_path,
        "--key",
        key_file(tmp_path, key_a),
        "--id",
        "urn:uuid:issued-2",
        "--now",
        VALID_FROM,
    ]
    first = run(argv)[1]
    second = run(argv)[1]
    assert first == second


@pytest.mark.parametrize(
    "document_type", ["WorkReceipt", "VerificationVerdict", "BlameAttestation"]
)
def test_issue_supports_every_document_type(tmp_path, key_a, key_b, document_type):
    from conftest import blame_subject, verdict_subject

    receipt = make_receipt(key_a)
    subjects = {
        "WorkReceipt": work_receipt_subject(),
        "VerificationVerdict": verdict_subject(receipt),
        "BlameAttestation": blame_subject(receipt, receipt),
    }
    subject_path = write(tmp_path, "subject.json", subjects[document_type])
    code, out, _ = run(
        [
            "issue",
            subject_path,
            "--key",
            key_file(tmp_path, key_b),
            "--type",
            document_type,
            "--now",
            VALID_FROM,
        ]
    )
    assert code == EXIT_OK
    document = json.loads(out)
    assert document["type"] == ["VerifiableCredential", document_type]
    assert verify_document(document, now=NOW, supporting=[receipt])["valid"] is True


def test_issue_reports_an_unusable_key_file(tmp_path):
    subject_path = write(tmp_path, "subject.json", work_receipt_subject())
    bad_key = tmp_path / "bad.key"
    bad_key.write_text("this is not a key", encoding="utf-8")
    code, out, err = run(["issue", subject_path, "--key", str(bad_key)])
    assert code == EXIT_USAGE
    assert out == ""
    assert "--key" in err


def test_issue_refuses_an_invalid_subject(tmp_path, key_a):
    subject_path = write(tmp_path, "subject.json", {"work": {}})
    code, out, err = run(
        ["issue", subject_path, "--key", key_file(tmp_path, key_a), "--now", VALID_FROM]
    )
    assert code == EXIT_INVALID
    assert out == ""
    assert "AWR-RCPT" in err


def test_issue_accepts_every_documented_key_file_form(tmp_path, key_a):
    from awr.multibase import multibase_encode_base58btc

    subject_path = write(tmp_path, "subject.json", work_receipt_subject())
    forms = {
        "jwk.json": json.dumps(key_a.private_key_jwk()),
        "seed.json": json.dumps({"privateKeySeedHex": key_a.seed_hex()}),
        "multibase.json": json.dumps(
            {
                "privateKeyMultibase": multibase_encode_base58btc(
                    b"\x80\x26" + bytes.fromhex(key_a.seed_hex())
                )
            }
        ),
        "raw.hex": key_a.seed_hex(),
    }
    for name, text in forms.items():
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        code, out, _ = run(
            [
                "issue",
                subject_path,
                "--key",
                str(path),
                "--id",
                "urn:uuid:issued-3",
                "--now",
                VALID_FROM,
            ]
        )
        assert code == EXIT_OK, name
        assert json.loads(out)["issuer"]["id"] == key_a.did


# ---------------------------------------------------------------------------
# exit codes and stream discipline
# ---------------------------------------------------------------------------


def test_exit_code_3_for_an_unimplemented_subcommand():
    code, out, err = run(["frobnicate", "file.json"])
    assert code == EXIT_UNIMPLEMENTED
    assert out == ""
    assert "not implemented" in err


def test_exit_code_2_for_a_missing_file():
    code, out, err = run(["verify", "/nonexistent/path/receipt.awr.json"])
    assert code == EXIT_USAGE
    assert out == ""
    assert err != ""


def test_exit_code_2_when_no_subcommand_is_given():
    code, out, err = run([])
    assert code == EXIT_USAGE
    assert out == ""
    assert "subcommand" in err


def test_exit_code_2_for_an_unknown_profile(tmp_path, key_a):
    path = write(tmp_path, "receipt.awr.json", make_receipt(key_a))
    code, out, _ = run(["verify", path, "--profile", "L9"])
    assert code == EXIT_USAGE
    assert out == ""


@pytest.mark.parametrize("subcommand", ["verify", "canonicalize", "digest", "hashdata"])
def test_every_subcommand_writes_only_its_payload_to_stdout(tmp_path, key_a, subcommand):
    path = write(tmp_path, "receipt.awr.json", make_receipt(key_a))
    argv = [subcommand, path]
    if subcommand == "verify":
        argv += ["--now", NOW]
    code, out, err = run(argv)
    assert code == EXIT_OK
    assert out != ""
    assert "awr:" not in out
    assert "error" not in out.lower() or subcommand == "verify"


# ---------------------------------------------------------------------------
# python -m awr, out of process
# ---------------------------------------------------------------------------


def _subprocess(argv, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = PACKAGE_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [PYTHON, "-m", "awr"] + argv,
        cwd=cwd or PACKAGE_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_python_dash_m_awr_verify_end_to_end(tmp_path, key_a):
    path = write(tmp_path, "receipt.awr.json", make_receipt(key_a))
    done = _subprocess(["verify", path, "--now", NOW])
    assert done.returncode == 0, done.stderr.decode()
    assert json.loads(done.stdout.decode())["valid"] is True
    assert done.stderr == b""


def test_python_dash_m_awr_canonicalize_emits_exact_bytes(tmp_path):
    value = {"b": [1, 2], "a": "x"}
    path = write(tmp_path, "value.json", value)
    done = _subprocess(["canonicalize", path])
    assert done.returncode == 0, done.stderr.decode()
    assert done.stdout == canonicalize(value)


def test_python_dash_m_awr_exit_code_1_on_an_invalid_document(tmp_path, key_a):
    receipt = make_receipt(key_a)
    receipt["id"] = "urn:uuid:renamed"
    path = write(tmp_path, "broken.awr.json", receipt)
    done = _subprocess(["verify", path, "--now", NOW])
    assert done.returncode == 1
    assert b"AWR-PROOF-006" in done.stderr
