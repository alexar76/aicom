"""Local teaching reconstruction; no network, real money, or dependencies.

Not a full MCP server or a replication of the original 78-run experiment.
The in-memory ledger illustrates a separate billing state; it is not durable.
"""
import json


class MockLedger:
    def __init__(self):
        self.total = 0
        self.keys = set()

    def charge(self, key=None):
        if key is not None and key in self.keys:
            return
        self.total += 7
        if key is not None:
            self.keys.add(key)


def lookup(args, ledger, *, billing=True, outcome="success", require_mode=False):
    if require_mode and "mode" not in args:
        raise ValueError("Missing required mode")
    mode = args.get("mode", "purchase")
    if mode not in ("preview", "purchase"):
        raise ValueError("Invalid mode")
    if billing and mode == "purchase":
        ledger.charge(args.get("idempotencyKey"))
    if outcome == "error":
        return {"isError": True, "message": "Record lookup unavailable"}
    if outcome == "timeout":
        raise TimeoutError("Response unavailable after mock charge")
    return {"recordId": "demo-record", "status": "available"}


def run_case(name, arguments, expected, **options):
    ledger = MockLedger()  # Every case starts with a fresh ledger.
    replies = []
    for args in arguments:
        try:
            replies.append({"kind": "result", "body": lookup(args, ledger, **options)})
        except (ValueError, TimeoutError) as error:
            replies.append({"kind": type(error).__name__, "message": str(error)})
    assert ledger.total == expected, (name, ledger.total, expected)
    return {"case": name, "calls": len(arguments),
            "replies": replies, "mockCredits": ledger.total}


def main():
    cases = [
        run_case("explicit-preview", [{"mode": "preview"}], 0),
        run_case("empty-default-purchase", [{}], 7),
        run_case("billing-disabled", [{}], 0, billing=False),
        run_case("charge-before-tool-error", [{}], 7, outcome="error"),
        run_case("charge-before-timeout", [{}], 7, outcome="timeout"),
        run_case("required-mode-empty", [{}], 0, require_mode=True),
        run_case("same-key-retry", [{"mode": "purchase", "idempotencyKey": "one-order"},
                                    {"mode": "purchase", "idempotencyKey": "one-order"}], 7),
    ]
    assert cases[1]["replies"] == cases[2]["replies"]
    assert cases[3]["replies"][0]["body"]["isError"] is True
    assert cases[4]["replies"][0]["kind"] == "TimeoutError"
    assert cases[5]["replies"][0]["kind"] == "ValueError"
    assert len(cases[6]["replies"]) == 2
    print(json.dumps({
        "scope": "Educational in-memory reconstruction; not a full MCP server or the original experiment",
        "realMoneyUsed": False,
        "networkUsed": False,
        "casesChecked": len(cases),
        "sameReplyDifferentBilling": True,
        "cases": cases,
    }, indent=2))


if __name__ == "__main__":
    main()
