import json
from histor.subject import MtlError, tool_set_digest


def tools(default):
    return [{
        "name": "demo", "description": "A fixture.",
        "inputSchema": {"type": "object", "properties": {
            "ratio": {"type": "number", "default": default}
        }}
    }]


digest, _ = tool_set_digest(tools(0.5))
assert digest == tool_set_digest(tools(5e-1))[0]
print(digest)

try:
    tool_set_digest(tools(json.loads("1e400")))
except MtlError as error:
    print(error.code)
