"""Recompute the N01 fixture's exported admission and nested identities offline."""

import hashlib
import json
from pathlib import Path


def identity(leaf, material, prefix=True):
    domain = f"hedgehog.common_action.{leaf}.v01".encode("ascii")
    payload = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    envelope = (
        b"HEDGEHOG_KERNEL_V01\x00" + len(domain).to_bytes(4, "big") + domain
        + len(payload).to_bytes(8, "big") + payload
    )
    digest = hashlib.sha256(envelope).hexdigest()
    return f"{leaf}:{digest}" if prefix else digest


def check_equal(label, actual, expected):
    if actual != expected:
        raise SystemExit(f"{label}: expected {expected!r}, got {actual!r}")


def verify_snapshot(snapshot):
    material = snapshot["native_material"]
    record = dict(material)
    definition_material = record["definition"]
    definition = dict(definition_material)
    sources = record["code_sources"]
    code_hashes = {}
    for pairs in sources:
        source = dict(pairs)
        symbol = source["public_symbol"]
        digest = hashlib.sha256(source["source_utf8"].encode("utf-8")).hexdigest()
        check_equal(symbol, digest, source["source_sha256"])
        code_hashes[symbol] = digest
    check_equal("definition code hashes", [list(pair) for pair in code_hashes.items()], definition["code_sha256s"])

    inputs = definition["input_validator_ref"]
    outputs = definition["output_validator_ref"]
    input_ref = identity("capability_input_contract", [
        ["input_fields", definition["input_fields"]],
        ["business_semantics", definition["business_semantics"]],
        ["input_validator_ref", inputs],
        ["input_validator_code_sha256", code_hashes[inputs]],
    ])
    output_ref = identity("capability_output_contract", [
        ["output_fields", definition["output_fields"]],
        ["output_validator_ref", outputs],
        ["output_validator_code_sha256", code_hashes[outputs]],
    ])
    check_equal("input contract", input_ref, record["input_contract_ref"])
    check_equal("output contract", output_ref, record["output_contract_ref"])
    contract = identity("capability_contract", [
        ["input_contract_ref", input_ref], ["output_contract_ref", output_ref],
    ], prefix=False)
    check_equal("combined contract", contract, definition["contract_sha256"])
    check_equal("definition", identity(
        "capability_definition", [pair for pair in definition_material if pair[0] != "definition_id"],
    ), definition["definition_id"])
    check_equal("implementation", identity("capability_implementation", [["code_sources", sources]]),
                record["implementation_ref"])
    check_equal("admission", identity("capability_admission", material), snapshot["admission_id"])


if __name__ == "__main__":
    fixture = json.loads(Path(__file__).with_name("n01-fixture.json").read_text(encoding="utf-8"))
    for name, snapshot in fixture["snapshots"].items():
        verify_snapshot(snapshot)
        check_equal("binding admission", fixture["bindings_to_sign"][name]["implementation_admission"],
                    snapshot["admission_id"])
        print(f"{name}: {snapshot['admission_id']} verified")
