"""Check only reviewed pure format_price ASTs; no service imports or execution."""
import ast
import __future__
from decimal import Decimal
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CASES = [
    ("0", "$0.00"),
    ("1", "$0.000001"),
    ("10", "$0.00001"),
    ("100", "$0.0001"),
    ("1000", "$0.001"),
    ("3000", "$0.003"),
    ("5000", "$0.005"),
    ("6000", "$0.006"),
    ("9999", "$0.009999"),
    ("10000", "$0.01"),
    ("10001", "$0.010001"),
    ("30000", "$0.03"),
    ("50000", "$0.05"),
    ("500000", "$0.50"),
    ("1000000", "$1.00"),
    ("123456789", "$123.456789"),
]


def extract(path):
    source = path.read_text()
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "format_price"]
    assert len(functions) == 1
    function = functions[0]
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom, ast.AsyncFunctionDef))
                   for n in ast.walk(function))
    constants = [n for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "KNOWN_ASSET_DECIMALS"
                         for t in n.targets)]
    assert len(constants) == 1
    decimals = ast.literal_eval(constants[0].value)
    namespace = {"KNOWN_ASSET_DECIMALS": decimals, "Decimal": Decimal}
    module = ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[]))
    exec(compile(module, str(path), "exec", flags=__future__.annotations.compiler_flag), namespace)
    return namespace["format_price"], function, decimals


rows = []
for repo in ["route-verdict", "list-smith", "lock-smith"]:
    path = OUT / repo / "app/parsers.py"
    function, node, assets = extract(path)
    sha = json.loads((OUT / (repo + "-commit.json")).read_text())["sha"]
    tests = []
    for units, expected in CASES:
        actual = function(units, "eip155:8453", USDC)
        assert actual == expected, (repo, units, actual, expected)
        assert Decimal(actual[1:]) == Decimal(units) / Decimal(1000000)
        tests.append({"units": units, "expected": expected, "actual": actual})
    edge_tests = [
        (None, "eip155:8453", USDC, None),
        ("not-a-number", "eip155:8453", USDC, None),
        ("1000", "eip155:8453", "0x0000000000000000000000000000000000000001", None),
        ("1000", "eip155:1", USDC, None),
    ]
    for units, network, asset, expected in edge_tests:
        actual = function(units, network, asset)
        assert actual == expected
        tests.append({"units": units, "network": network, "asset": asset,
                      "expected": expected, "actual": actual})
    rows.append({
        "repo": repo, "commit": sha,
        "source": f"https://github.com/QuincyGB/{repo}/blob/{sha}/app/parsers.py#L{node.lineno}",
        "function_start_line": node.lineno, "function_end_line": node.end_lineno,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "known_asset_entries": len(assets), "tests_passed": len(tests), "tests": tests,
    })

old = OUT.parents[1] / "quincygb-verification-2026-10-29/source-review/route-verdict/app/parsers.py"
old_function, _, _ = extract(old)
old_examples = [{"units": units,
                 "old_output": old_function(units, "eip155:8453", USDC),
                 "new_output": expected}
                for units, expected in CASES if units in ("1", "1000", "5000", "10001")]
result = {
    "method": "Only reviewed pure format_price FunctionDef AST nodes executed in memory; "
              "KNOWN_ASSET_DECIMALS loaded through ast.literal_eval. No third-party module imports, "
              "network, database, service startup, payments or messages.",
    "old_baseline_examples": old_examples,
    "precision_coverage": "16 exact-price cases per repository, covering zero, 1 micro-USDC, "
                          "the original 0.001/0.005 regressions, sub-cent residue above 0.01, "
                          "cent values and 123.456789; plus 4 unknown/invalid cases. "
                          "This is bounded test coverage of known Base USDC (6 decimals), "
                          "not an exhaustive claim for every integer magnitude or unknown token.",
    "repositories": rows, "total_asserted_cases": sum(x["tests_passed"] for x in rows),
    "result": "All 60 cases passed; the two original sub-cent display regressions are fixed in source.",
    "production_deployment_verified": False,
}
(OUT / "price-fix-reproduction.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: v for k, v in result.items() if k != "repositories"}, ensure_ascii=False, indent=2))
print(json.dumps([{k: v for k, v in x.items() if k != "tests"} for x in rows], ensure_ascii=False, indent=2))
