"""Run reviewed pure functions only; never import or start third-party modules."""
import ast
import __future__
import copy
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
NS = {
    "json": json,
    "hashlib": hashlib,
    "KNOWN_ASSET_DECIMALS": {
        ("eip155:8453", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"): 6
    },
}
SELECTED = {
    "route-verdict/app/parsers.py": ["format_price"],
    "route-verdict/app/schema_quality.py": [
        "_schema_types_real_fields", "_untyped_property_count", "evaluate_schema_quality"
    ],
    "route-verdict/app/checker.py": ["_comparables", "compute_diff"],
    "stall-row/app/services/recheck.py": ["_hash_text", "_x402_fingerprint", "_diff"],
}
provenance = []
for path, names in SELECTED.items():
    tree = ast.parse((OUT / path).read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for f in nodes for n in ast.walk(f))
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    # The original files use future annotations too. Preserve that behavior
    # on the host Python, which otherwise evaluates the union annotations.
    exec(compile(module, path, "exec", flags=__future__.annotations.compiler_flag), NS)
    provenance.extend({"file": path, "function": n.name, "start_line": n.lineno,
                       "end_line": n.end_lineno} for n in nodes)

asset = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
prices = [{"amount_units": str(n), "exact_usdc": str(n / 1000000),
           "actual_format_price_output": NS["format_price"](str(n), "eip155:8453", asset)}
          for n in [1000, 3000, 5000, 6000, 30000, 50000]]
assert prices[0]["actual_format_price_output"] == "$0.00"
assert prices[2]["actual_format_price_output"] == "$0.01"

bazaar = {
    "info": {
        "input": {"type": "http", "method": "POST", "body": {"value": "sample"}},
        "output": {"type": "json", "schema": {"type": "object", "properties": {
            "value": {"type": "string"}}}, "example": {"value": "sample"}},
    },
    "schema": {"type": "object", "properties": {"input": {"type": "object"}}},
}
changed = copy.deepcopy(bazaar)
changed["info"]["output"]["schema"]["properties"]["value"]["type"] = "number"
changed["info"]["output"]["example"]["value"] = 1
quality_before = NS["evaluate_schema_quality"](bazaar, "fixture")
quality_after = NS["evaluate_schema_quality"](changed, "fixture")


def route_result(quality, stamp):
    return {"checked_at": stamp, "liveness": {"alive": True}, "terms": {
        "amount_units": "1000", "asset": asset, "pay_to": "seller", "network": "eip155:8453"},
        "schema_quality": quality, "catalog": {
            "cdp_bazaar": {"status": "listed"}, "payai": {"status": "listed"}}}


route_diff = NS["compute_diff"](
    route_result(quality_before, "2026-10-29T11:00:00Z"),
    route_result(quality_after, "2026-10-29T11:01:00Z"),
)
assert quality_before["score"] == quality_after["score"] == 100
assert route_diff["changes"] == []

base = {
    "x402Version": 2, "resource": {"description": "fixture"},
    "accepts": [
        {"scheme": "exact", "amount": "1000", "asset": asset,
         "network": "eip155:8453", "payTo": "seller"},
        {"scheme": "exact", "amount": "2000", "asset": asset,
         "network": "eip155:1", "payTo": "seller2"},
    ],
    "extensions": {"bazaar": bazaar},
}
custom = copy.deepcopy(base)
custom["extensions"]["bazaar"] = changed
fingerprint_before = NS["_x402_fingerprint"](402, base)
positive = NS["_diff"](fingerprint_before, NS["_x402_fingerprint"](402, custom))
assert {x["field"] for x in positive} == {"schema_hash"}

negative_cases = []
for name, mutate in [
    ("input_method", lambda d: d["extensions"]["bazaar"]["info"]["input"].update(method="GET")),
    ("standard_bazaar_schema", lambda d: d["extensions"]["bazaar"]["schema"].update(required=["input"])),
    ("second_accept_amount", lambda d: d["accepts"][1].update(amount="99000")),
    ("primary_scheme", lambda d: d["accepts"][0].update(scheme="upto")),
]:
    candidate = copy.deepcopy(base)
    mutate(candidate)
    fingerprint = NS["_x402_fingerprint"](402, candidate)
    diff = NS["_diff"](fingerprint_before, fingerprint)
    assert diff == []
    negative_cases.append({"change": name, "diff": diff})

result = {
    "method": "Source-level in-memory execution of only reviewed pure FunctionDef AST nodes. "
              "Imports, module initialization, IO, network, database and service execution excluded. "
              "Exact functions listed in provenance. No live paid calls.",
    "function_provenance": provenance,
    "price_formatting": prices,
    "routeverdict_schema_only_change": {
        "before_schema": bazaar["info"]["output"]["schema"],
        "after_schema": changed["info"]["output"]["schema"],
        "quality_before": quality_before, "quality_after": quality_after,
        "actual_compute_diff": route_diff,
    },
    "recheck_positive_control_same_schema_change": positive,
    "recheck_not_monitored_cases": negative_cases,
    "assertions_passed": True,
}
(OUT / "source-pure-function-reproduction.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
