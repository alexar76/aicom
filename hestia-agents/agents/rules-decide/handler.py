"""Deterministic policy decision with a rule trace.

Pure function: no clock, no randomness, no I/O. The same policy and the same
facts always produce the same decision — which is the only reason the Ed25519
signature on the response is worth anything. A nondeterministic handler makes
its own receipt unverifiable.

First matching rule wins, in the order the policy lists them.
"""

import decimal
import hashlib
import json
import re

MAX_RULES = 200
MAX_CONDITIONS = 50
MAX_PATTERN = 200
MAX_SUBJECT = 10000


def _decimal(value):
    """Decimal for a JSON number, else None. Bools are not numbers here."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return decimal.Decimal(value)
    if isinstance(value, float):
        try:
            return decimal.Decimal(str(value))
        except decimal.InvalidOperation:
            return None
    return None


def _compare(op, actual, expected):
    """Return (ok, note). `note` explains a False that is not simply 'different'."""
    if op == "exists":
        want = bool(expected) if expected is not None else True
        return ((actual is not None) == want, "")
    if actual is None:
        return (False, "fact is missing")
    if op == "==":
        return (actual == expected, "")
    if op == "!=":
        return (actual != expected, "")
    if op in ("in", "not_in"):
        if not isinstance(expected, list):
            return (False, "value for in/not_in must be a list")
        inside = actual in expected
        return (inside if op == "in" else not inside, "")
    if op == "matches":
        if not isinstance(actual, str) or not isinstance(expected, str):
            return (False, "matches needs a string fact and a string pattern")
        if len(expected) > MAX_PATTERN:
            return (False, "pattern is too long")
        if len(actual) > MAX_SUBJECT:
            return (False, "subject is too long")
        try:
            return (re.fullmatch(expected, actual) is not None, "")
        except re.error:
            return (False, "pattern is not a valid regular expression")
    left = _decimal(actual)
    right = _decimal(expected)
    if left is None or right is None:
        return (False, "both sides must be numbers for " + op)
    if op == "<":
        return (left < right, "")
    if op == "<=":
        return (left <= right, "")
    if op == ">":
        return (left > right, "")
    if op == ">=":
        return (left >= right, "")
    return (False, "unknown operator")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def handle(payload):
    policy = payload.get("policy")
    facts = payload.get("facts")
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    if not isinstance(facts, dict):
        raise ValueError("facts must be an object")
    rules = policy.get("rules")
    if not isinstance(rules, list):
        raise ValueError("policy.rules must be a list")
    if len(rules) > MAX_RULES:
        raise ValueError("policy has too many rules")

    trace = []
    outcome = None
    matched_rule = None
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError("every rule must be an object")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            rule_id = "rule[" + str(index) + "]"
        conditions = rule.get("when", [])
        if not isinstance(conditions, list):
            raise ValueError("rule '" + rule_id + "' has a non-list 'when'")
        if len(conditions) > MAX_CONDITIONS:
            raise ValueError("rule '" + rule_id + "' has too many conditions")
        checked = []
        all_ok = True
        for condition in conditions:
            if not isinstance(condition, dict):
                raise ValueError("every condition must be an object")
            fact_name = condition.get("fact")
            op = condition.get("op", "==")
            expected = condition.get("value")
            if not isinstance(fact_name, str) or not fact_name:
                raise ValueError("condition needs a 'fact' name")
            if not isinstance(op, str):
                raise ValueError("condition 'op' must be a string")
            actual = facts.get(fact_name)
            ok, note = _compare(op, actual, expected)
            entry = {
                "fact": fact_name,
                "op": op,
                "expected": expected,
                "actual": actual,
                "ok": ok,
            }
            if note:
                entry["note"] = note
            checked.append(entry)
            if not ok:
                all_ok = False
        # Record every rule that was considered, so a reader can see why the
        # earlier ones did not fire rather than only which one did.
        trace.append({"rule": rule_id, "matched": all_ok, "conditions": checked})
        if all_ok:
            then = rule.get("then")
            if not isinstance(then, dict):
                raise ValueError("rule '" + rule_id + "' matched but has no 'then' object")
            outcome = then
            matched_rule = rule_id
            break

    if outcome is None:
        fallback = policy.get("default")
        if not isinstance(fallback, dict):
            raise ValueError("no rule matched and policy has no 'default' object")
        outcome = fallback

    policy_id = policy.get("id")
    if not isinstance(policy_id, str):
        policy_id = ""
    return {
        "decision": outcome.get("decision"),
        "reason": outcome.get("reason"),
        "outcome": outcome,
        "matched_rule": matched_rule,
        "rules_considered": len(trace),
        "trace": trace,
        "policy_id": policy_id,
        "policy_sha256": hashlib.sha256(_canonical(policy).encode("utf-8")).hexdigest(),
        "facts_sha256": hashlib.sha256(_canonical(facts).encode("utf-8")).hexdigest(),
    }
