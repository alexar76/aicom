"""Validate v1 aggregate reports and replay the synthetic comparison cases."""

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import hmac
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import rfc8785


HERE = Path(__file__).resolve().parent
PUBLIC_DOMAIN = b"aimarket.x402-example-replay/public/v1\x00"
PRIVATE_DOMAIN = b"aimarket.x402-example-replay/private/v1\x00"


def unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON key")
    return result


def reject_constant(_):
    raise ValueError("non-finite JSON number")


def load(path):
    with path.open("rb") as file:
        raw = file.read(65_537)
    if len(raw) > 65_536:
        raise ValueError("JSON input exceeds 64 KiB")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)


def validate(record):
    validator = Draft202012Validator(load(HERE / "aggregate.schema.json"),
                                    format_checker=Draft202012Validator.FORMAT_CHECKER)
    error = next(validator.iter_errors(record), None)
    if error is not None:
        raise ValueError(f"invalid aggregate at {error.json_path}: {error.validator}")
    scope = record["scope"]
    if scope["fromDate"] >= scope["untilDate"]:
        raise ValueError("aggregate window must advance")

    counts = record["counts"]
    external = counts["externalSettledPayments"]
    classified = counts["exampleMatches"] + counts["exampleMismatches"]
    if external > counts["settledPayments"] or classified + counts["unclassified"] != external:
        raise ValueError("inconsistent settlement counts")
    payers = counts["externalPayers"]
    matched = counts["exampleMatchedPayers"]
    if not (bool(external) == bool(payers) and matched <= payers <= external
            and bool(matched) == bool(counts["exampleMatches"])
            and matched <= counts["exampleMatches"]
            and payers - matched <= external - counts["exampleMatches"]):
        raise ValueError("inconsistent payer counts")


def public_digest(report, body):
    envelope = {"network": report["scope"]["network"], "resourceId": report["scope"]["resourceId"],
                "exampleId": report["comparison"]["exampleId"], "input": body}
    return hashlib.sha256(PUBLIC_DOMAIN + rfc8785.dumps(envelope)).digest()


def private_tag(report, body, key, nonce):
    if len(key) != 32 or len(nonce) != 16:
        raise ValueError("expected 32-byte key and 16-byte comparison nonce")
    envelope = {"scope": report["scope"], "exampleId": report["comparison"]["exampleId"],
                "nonceHex": nonce.hex(), "input": body}
    return hmac.digest(key, PRIVATE_DOMAIN + rfc8785.dumps(envelope), "sha256")


def require(condition, case):
    if not condition:
        raise ValueError(f"fixture check failed: {case}")


def run_fixture(fixture):
    report = fixture["aggregate"]
    validate(report)
    require(report["dataOrigin"] == "synthetic", "fixture uses synthetic data")
    sample = fixture["example"]
    other_scope = deepcopy(report)
    other_scope["scope"]["resourceId"] = "different-resource-v1"

    if report["comparison"]["method"] == "public-jcs-sha256":
        def digest(record, value):
            return public_digest(record, value)

        expected = report["comparison"]["publicExampleSha256"]
    else:
        key = bytes.fromhex(fixture["syntheticKeyHex"])
        nonce = bytes.fromhex(fixture["syntheticNonceHex"])

        def digest(record, value):
            return private_tag(record, value, key, nonce)

        expected = fixture["syntheticReferenceTagHex"]
        require(private_tag(report, sample, bytes(32), nonce).hex() != expected, "wrong key")
        require(private_tag(report, sample, key, bytes(16)).hex() != expected, "different nonce")
        require(public_digest(report, sample).hex() != expected, "public digest cannot substitute for private tag")
        different_window = deepcopy(report)
        different_window["scope"]["untilDate"] = "2026-01-09"
        require(digest(different_window, sample).hex() != expected, "different private window")

    reference = digest(report, sample)
    require(reference.hex() == expected, "pinned reference")
    require(digest(other_scope, sample) != reference, "different resource scope")
    counts = Counter()
    payers = set()
    matched_payers = set()
    for candidate in fixture["syntheticPayments"]:
        body = candidate["input"]
        outcome = "unclassified"
        if body is not None:
            same = hmac.compare_digest(reference, digest(report, body))
            outcome = "exampleMatches" if same else "exampleMismatches"
        require(outcome == candidate["expected"], f"payment classified as {outcome}")
        counts[outcome] += 1
        payers.add(candidate["syntheticPayerId"])
        if outcome == "exampleMatches":
            matched_payers.add(candidate["syntheticPayerId"])
    external = len(fixture["syntheticPayments"])
    observed = {
        "settledPayments": external + fixture["syntheticOperatorSettlements"],
        "externalSettledPayments": external,
        "externalPayers": len(payers),
        "exampleMatchedPayers": len(matched_payers),
        **{key: counts[key] for key in ("exampleMatches", "exampleMismatches", "unclassified")},
    }
    require(observed == report["counts"], "all reported counts recomputed")
    print(f"PASS {report['comparison']['method']}")


def reject_invalid_reports(public, private):
    cases = [
        (public, ("scope", "fromDate"), "2026-02-30"),
        (public, ("scope", "untilDate"), public["scope"]["fromDate"]),
        (public, ("counts", "externalSettledPayments"), public["counts"]["settledPayments"] + 1),
        (public, ("counts", "exampleMatchedPayers"), public["counts"]["exampleMatches"] + 1),
        (public, ("scope", "transaction"), "synthetic-forbidden-field"),
        (public, ("comparison", "publicExampleSha256"), "0"),
        (private, ("comparison", "publicExampleSha256"), "0" * 64),
    ]
    for record, (section, key), value in cases:
        changed = deepcopy(record)
        changed[section][key] = value
        try:
            validate(changed)
        except ValueError:
            continue
        raise ValueError(f"invalid aggregate accepted: {section}.{key}")
    print(f"PASS {len(cases)} malformed aggregate controls")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", type=Path, help="validate the shape and counts of one aggregate")
    args = parser.parse_args()
    if args.validate:
        validate(load(args.validate))
        print("PASS aggregate shape and count constraints")
    else:
        public = load(HERE / "public.fixture.json")
        private = load(HERE / "private.fixture.json")
        run_fixture(public)
        run_fixture(private)
        reject_invalid_reports(public["aggregate"], private["aggregate"])


if __name__ == "__main__":
    main()
