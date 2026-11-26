"""Where mcp-hangar's per-tool digest rule and mcp-tool-set-digest/1 section 9 give different bytes.

Hangar's rule is re-implemented here from its source (src/mcp_hangar/domain/services/digest_computation.py,
commit 57a691edbcb7 of 2026-10-16): JCS over {name, description, inputSchema, outputSchema} where a member
that is None, "", {} or [] is left out. Hangar's own code and its `jcs` dependency were NOT run; the JCS
text comes from this repository's reference implementation, so differences in the canonicalizer itself
(numbers, escapes, duplicate names) are outside this comparison.

Usage: python3 -B compare_rules.py ../../mcp-tool-set-digest > comparison.json
"""
import collections, hashlib, json, sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "implementations/python"))
import tool_set_digest as tsd  # noqa: E402


def hangar_entry(tool):
    name = tool.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("no name")
    out = {"name": name}
    for field in ("description", "inputSchema", "outputSchema"):
        v = tool.get(field)
        if v is None or (isinstance(v, (dict, list, str)) and len(v) == 0):
            continue
        out[field] = v
    return out


def why(tool):
    reasons = []
    d, i, o = tool.get("description"), tool.get("inputSchema"), tool.get("outputSchema")
    if "description" not in tool or d is None or d == "":
        reasons.append("description absent or empty: spec writes \"\", Hangar omits the member")
    elif not isinstance(d, str):
        reasons.append("description is not a string: spec reads it as \"\", Hangar keeps the value")
    if "inputSchema" not in tool or i is None or i == {}:
        reasons.append("inputSchema absent or {}: spec writes {}, Hangar omits the member")
    elif not isinstance(i, dict):
        reasons.append("inputSchema is not an object: spec reads it as {}, Hangar keeps the value")
    if o == {}:
        reasons.append("outputSchema is {}: spec keeps it (differs from absent), Hangar omits it")
    elif "outputSchema" in tool and o is not None and not isinstance(o, dict):
        reasons.append("outputSchema is not an object: spec leaves it out, Hangar keeps the value")
    return reasons or ["other"]


vectors = json.loads((root / "vectors/vectors.json").read_text())["vectors"]
same = differ = skipped_vectors = 0
reasons = collections.Counter()
examples = {}
for v in vectors:
    if "error" in v["contract"]:
        skipped_vectors += 1          # the spec gives these sets no digest at all
        continue
    try:
        tools = tsd.tools_of(tsd.parse(v["tools"]))
    except Exception:
        skipped_vectors += 1
        continue
    for t in tools:
        spec_hex = hashlib.sha256(tsd.canonical(tsd.contract_entry(t)).encode("utf-8")).hexdigest()
        try:
            hangar_hex = hashlib.sha256(tsd.canonical(hangar_entry(t)).encode("utf-8")).hexdigest()
        except tsd.DigestError as exc:   # Hangar keeps a value the spec reads as absent, and JCS has no text for it
            differ += 1
            reasons[f"kept value has no canonical text ({exc.args[0]})"] += 1
            examples.setdefault(f"kept value has no canonical text ({exc.args[0]})", v["id"])
            continue
        if spec_hex == hangar_hex:
            same += 1
        else:
            differ += 1
            for r in why(t):
                reasons[r] += 1
                examples.setdefault(r, v["id"])
json.dump({"hangarCommit": "57a691edbcb7", "vectors": len(vectors), "vectorsWithNoSpecDigest": skipped_vectors,
           "toolsCompared": same + differ, "samePerToolDigest": same, "different": differ,
           "reasons": dict(reasons.most_common()), "firstVectorPerReason": examples}, sys.stdout, indent=1)
print()
