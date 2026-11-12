"""Run the same eight local inputs through the actual MTL 1.0 and 1.1 sources."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
REFERENCE = "awr/adoption/mcp-trust-label/tools/mtl_subject.py"
sys.path.insert(0, str(ROOT / "awr/reference/python"))
from awr import AwrError


def load(name, source):
    path = HERE / (name + ".py")
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


old = load("mtl_1_0_snapshot", subprocess.check_output(["git", "show", "8e0763168^:" + REFERENCE], cwd=ROOT, text=True))
v11_source = subprocess.check_output(["git", "show", "8e0763168:" + REFERENCE], cwd=ROOT, text=True)
v11 = load("mtl_1_1_snapshot", v11_source)
current_source = (ROOT / REFERENCE).read_text()
assert current_source == v11_source, "The digest implementation changed since revision 1.1"


def tool(value):
    return {"name": "demo", "description": "A fixture.", "inputSchema": {"type": "object", "properties": {"ratio": {"type": "number", "default": value}}}}


fixtures = [("integer default 1", [tool(1)]), ("fraction 0.5", [tool(0.5)]),
            ("exponent 1e21", [tool(1e21)]), ("integer 2^53 + 1", [tool(2**53 + 1)]),
            ("empty tool list", []), ("repeated tool names", [tool(1), tool(2)]),
            ("entry without a name", [{"description": "A fixture."}]),
            ("overflow 1e400", [tool(json.loads("1e400"))])]
rows = []
for label, tools in fixtures:
    row = {"fixture": label}
    for name, mod in (("1.0", old), ("1.1", v11)):
        try:
            digest, _ = mod.tool_set_digest(copy.deepcopy(tools))
            row[name] = {"digest": digest, "status": "digested"}
        except (mod.MtlError, AwrError) as error:
            row[name] = {"status": "declined", "code": error.code}
    rows.append(row)
assert rows[0]["1.0"]["digest"] == rows[0]["1.1"]["digest"]
assert all(row["1.0"]["status"] == "declined" and row["1.1"]["status"] == "digested" for row in rows[1:6])
assert all(row["1.0"]["status"] == row["1.1"]["status"] == "declined" for row in rows[6:])
assert v11.tool_set_digest([tool(2**53+1)])[0] == v11.tool_set_digest([tool(2**53)])[0]
(HERE / "fixture-results.json").write_text(json.dumps({"kind": "offline implementation fixtures, not a production survey", "source10": "8e0763168^", "source11": "8e0763168", "currentDigestSourceByteIdenticalTo11": True, "rows": rows}, indent=2) + "\n")
print(json.dumps(rows, indent=2))
