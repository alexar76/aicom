"""Prove that the startup regression catches the original annotation failure, without source edits."""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLUGIN = ROOT / "plugins/aimarket-oracle-gateway"
TEST = PLUGIN / "tests/test_stdio_startup.py"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location("oracle_startup_regression", TEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = PLUGIN / "aimarket_oracle_gateway/mcp_tool_surface.py"
    original_sha = sha256(source)
    with tempfile.TemporaryDirectory(prefix="annotation-control-", dir=HERE) as directory:
        temporary = Path(directory)
        healthy = temporary / "healthy"
        healthy.mkdir()
        initialized, tools = module._startup(PLUGIN, healthy)
        assert initialized["serverInfo"]["version"] == "0.3.2" and len(tools) == 36

        mutant_root = temporary / "mutant"
        shutil.copytree(PLUGIN / "aimarket_oracle_gateway", mutant_root / "aimarket_oracle_gateway",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        mutant = mutant_root / "aimarket_oracle_gateway/mcp_tool_surface.py"
        lines = mutant.read_text(encoding="utf-8").splitlines(keepends=True)
        tree = ast.parse("".join(lines))
        assert isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant)
        assert isinstance(tree.body[0].value.value, str)
        assert "from __future__ import annotations" not in "".join(lines)
        lines.insert(tree.body[0].end_lineno, "\nfrom __future__ import annotations\n")
        mutant.write_text("".join(lines), encoding="utf-8")
        failed = temporary / "failed"
        failed.mkdir()
        try:
            module._startup(mutant_root, failed)
        except AssertionError as error:
            failure = str(error)
        else:
            raise AssertionError("startup regression accepted the restored annotation bug")
        assert "exited before answering initialize" in failure, failure
        assert all(text in failure for text in ("ValuesList", "InvalidSignature", "aggregate_values")), failure
        (HERE / "negative-control-stderr.log").write_bytes((failed / "oracle-startup-stderr.log").read_bytes())
        result = {
            "runtime": {"python": sys.version.split()[0], "mcp": importlib.metadata.version("mcp")},
            "healthy": {"source": str(PLUGIN.relative_to(ROOT)), "serverVersion": initialized["serverInfo"]["version"],
                        "protocol": initialized["protocolVersion"], "tools": len(tools), "passed": True},
            "negativeControl": {"mutation": "Add only future annotations after mcp_tool_surface.py module docstring in a copied package",
                                "caughtBySameStartupHarness": True, "failedBeforeInitialize": True,
                                "cause": "ValuesList NameError wrapped as aggregate_values InvalidSignature",
                                "mutatedModuleSha256": sha256(mutant)},
            "workspaceSourceUnchanged": sha256(source) == original_sha,
            "sourceSha256": original_sha, "testSha256": sha256(TEST),
            "networkRequests": 0, "toolCalls": 0, "temporaryCopyRemoved": True,
        }
    assert sha256(source) == original_sha
    (HERE / "negative-control.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: current source starts; the same startup harness rejects a copied source with the original annotation bug")


if __name__ == "__main__":
    main()
