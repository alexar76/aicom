"""Exercise only reviewed pure AST functions; no third-party imports or IO."""
import ast
import __future__
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
selected = {
    "app/schema_quality.py": ["_schema_types_real_fields", "_untyped_property_count", "evaluate_schema_quality", "_type_signature", "_contract_fields", "schema_contract"],
    "app/checker.py": ["_comparables", "_contract_of", "_contract_change_entries", "compute_diff"],
}
ns = {"json": json, "_MAX_CONTRACT_CHANGES": 25}
provenance = []
for file, names in selected.items():
    parsed = ast.parse((ROOT / file).read_text())
    nodes = [n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for f in nodes for n in ast.walk(f))
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, file, "exec", flags=__future__.annotations.compiler_flag), ns)
    provenance.extend({"file": file, "function": n.name, "line": n.lineno} for n in nodes)

before = {"info": {"input": {"type": "http", "method": "POST", "body": {"value": "sample"}},
    "output": {"type": "json", "example": {"value": "sample"}, "schema": {
        "type": "object", "properties": {"value": {"type": "string"}}}}}}
after = copy.deepcopy(before)
after["info"]["output"]["schema"]["properties"]["value"]["type"] = "number"
after["info"]["output"]["example"]["value"] = 1


def result(extension, *, contract=True, score=None):
    quality = ns["evaluate_schema_quality"](extension, "fixture")
    if score is not None:
        quality["score"] = score
    if contract:
        quality["contract"] = ns["schema_contract"](extension)
    return {"checked_at": "2026-10-29T13:40:00Z", "liveness": {"alive": True},
        "terms": {"amount_units": "1000", "asset": "USDC", "pay_to": "fixture-seller", "network": "eip155:8453"},
        "schema_quality": quality, "catalog": {"cdp_bazaar": {"status": "listed"}, "payai": {"status": "listed"}}}


old, new = result(before), result(after)
assert old["schema_quality"]["score"] == new["schema_quality"]["score"] == 100
changed = ns["compute_diff"](old, new)
assert changed["schema_score_stability"] == "stable"
assert changed["contract_stability"] == "changed"
assert len(changed["changes"]) == 1
assert changed["changes"][0]["path"] == "$.value"
assert changed["changes"][0]["before"] == "string" and changed["changes"][0]["after"] == "number"

stable = ns["compute_diff"](old, copy.deepcopy(old))
assert stable["contract_stability"] == stable["schema_score_stability"] == "stable" and stable["changes"] == []
legacy = ns["compute_diff"](result(before, contract=False), old)
assert legacy["contract_stability"] == "unknown"
assert not [x for x in legacy["changes"] if x.get("kind") == "contract_change"]
first = ns["compute_diff"](None, old)
assert first["contract_stability"] == first["schema_score_stability"] == "unknown"
grade = ns["compute_diff"](result(before, score=90), old)
assert grade["schema_score_stability"] == "changed" and grade["contract_stability"] == "stable"
assert [x["field"] for x in grade["changes"]] == ["schema_score"]

report = {"commit": "5a36f743d0b2b9b6dd42ee075f25d138e738e166", "method": "Only reviewed pure AST functions; no service, third-party module initialization, network or database executed.",
    "function_provenance": provenance, "original_type_flip_case": changed, "identical_contract_control": stable,
    "legacy_record_case": legacy, "first_observation_case": first, "score_only_change_control": grade,
    "quality_scores": [old["schema_quality"]["score"], new["schema_quality"]["score"]], "assertions_passed": True,
    "limits": ["Fix verified for the original field-type case in pinned source, not a new paid production response.",
        "Contract identity is a selected output-schema field map, not complete semantic equivalence of every JSON Schema constraint."]}
(ROOT / "contract-fix-reproduction.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
