"""How each code-finding rule is fixed in THIS monorepo, for the remediation fixer's prompt and its self-check.

The first MOMUS code loop (2026-11-16) told the model only "VX-918-CHECK-THEN-CONNECT in search_v2". Three of the
five branches the gate passed resolved the name a second time and connected to that unchecked answer, over HTTPS to
a bare IP with no SNI: a shape that satisfies the rule and keeps the bug. The monorepo already has correct fixes for
every rule (the Vulnetix remediation, 5ad17c13a); the model had never seen them. This module names them, and the
reference functions are read from the current checkout of main (AIFACTORY_REMEDIATION_CODE_ROOT) at prompt time, so
a guide cannot drift from the code it points at.

It also runs the finding's own rule on the model's rewrite before a branch is pushed (`still_matches`): the scanner
is MOMUS's module in that same checkout, loaded by path, so the fixer and the gate use the same rules.
"""
from __future__ import annotations

import ast
import importlib.util
import logging
import os
import re
import sys
from typing import Any

logger = logging.getLogger(__name__)

#: Bytes of reference source per prompt: enough for the functions named below, not whole files.
MAX_GUIDE_REFERENCE_CHARS = 12_000

RULE_IN_TITLE = re.compile(r":\s*(?P<rule>VX-[A-Z0-9-]+)\s+in\s+(?P<function>\S+)")

GUIDES: dict[str, dict[str, Any]] = {
    "VX-918-CHECK-THEN-CONNECT": {
        "wrong": "The URL's host is checked (resolved and found public), and then the HTTP client connects by NAME "
                 "and resolves it again. DNS can answer differently the second time (rebinding), so the address "
                 "that was checked is not the one connected to.",
        "right": "Resolve once, check EVERY address that lookup returns, connect to an address that passed. Put that "
                 "address in the URL, keep the name in the Host header and, for HTTPS, in TLS SNI via httpx "
                 "`extensions={'sni_hostname': name}` so the certificate is still verified against the name.",
        "never": ["Calling getaddrinfo (or a helper) again after the check and connecting to that new, unchecked "
                  "answer. It is the same gap with one more step, and the gate now rejects it.",
                  "Requesting https://<ip>/ without Host and sni_hostname: the TLS handshake fails.",
                  "Adding `# vx-ok:` or any comment that silences the check."],
        "references": [("aimarket-mcp/aimarket_mcp/security.py", ("_non_public", "_validated_ips", "pin_target",
                                                                 "safe_post")),
                       ("atlas/atlas/delivery.py", ("_is_public", "_delivery_target"))],
    },
    "VX-918-UNPINNED-RETURN": {
        "wrong": "A helper that is meant to pin the target returns the URL it was given for HTTPS, so the caller "
                 "connects by name.",
        "right": "Return the checked address for every scheme, with the name for the Host header and sni_hostname.",
        "never": ["Leaving HTTPS on the name because 'pinning breaks TLS': sni_hostname keeps verification."],
        "references": [("aimarket-mcp/aimarket_mcp/security.py", ("_validated_ips", "pin_target"))],
    },
    "VX-FWD-HEADER-TRUST": {
        "wrong": "The caller's address is taken from X-Forwarded-For / X-Real-IP without first checking that the "
                 "socket peer is a proxy we run, so any direct caller chooses its own identity (rate limits, "
                 "tiers, lockouts).",
        "right": "Read the header only when request.client.host is in a configured list of trusted proxies "
                 "(CIDRs from the service's settings, default loopback), and take the RIGHT-most hop, the one the "
                 "proxy appended. Otherwise use the socket peer.",
        "never": ["Hard-coding all private ranges as trusted: other containers and hosts on those networks are not "
                  "our proxy.", "A yes/no flag that trusts the header from everyone once switched on."],
        "references": [("ai-service-mesh/backend/ai_service_mesh/security.py",
                        ("parse_trusted_proxies", "_peer_is_trusted_proxy", "client_ip")),
                       ("oracles/core/oracle_core/app.py", ("peer_is_local_proxy", "client_key"))],
    },
    "VX-306-OPEN-WITHOUT-KEY": {
        "wrong": "An auth check lets every caller in when no key is configured; outside production that is anyone "
                 "who can reach the port.",
        "right": "With no key configured, admit only callers on this machine (a loopback peer with a loopback Host "
                 "and no forwarding headers), or refuse.",
        "never": ["Returning True for 'demo' or 'development' without checking where the caller is."],
        "references": [("metis/metis/api/auth.py", ("_host_is_loopback", "local_caller"))],
    },
    "VX-SSH-NO-HOSTKEY": {
        "wrong": "ssh runs with host-key checking switched off, so the first key any host presents is trusted.",
        "right": "StrictHostKeyChecking=accept-new with a pinned known_hosts file; =no only for a remote on this "
                 "same machine.",
        "never": ["UserKnownHostsFile=/dev/null outside the local-remote case."],
        "references": [("skopos/skopos/remediation/git_push.py", ())],
    },
}


def rule_and_function(ticket: dict[str, Any]) -> tuple[str, str]:
    """(rule, function) from the part MOMUS signed: the Blame summary `path: RULE in function — ...` (the same
    text code_scope reads the path from). ("", "") when it is not a code finding."""
    m = RULE_IN_TITLE.search(str((ticket.get("blame") or {}).get("summary") or ""))
    return (m.group("rule"), m.group("function")) if m else ("", "")


def _functions(source: str, names: tuple[str, ...]) -> str:
    if not names:
        return source
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    lines = source.splitlines()
    parts = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            parts.append((node.lineno, "\n".join(lines[start - 1:node.end_lineno])))
    return "\n\n".join(text for _, text in sorted(parts))


def guide_block(ticket: dict[str, Any], code_root: str, read_is_denied=None, redact=None) -> str:
    """The prompt section for a code finding: what is wrong, the fix this repo uses, and that fix's source."""
    rule, function = rule_and_function(ticket)
    guide = GUIDES.get(rule)
    if not guide:
        return ""
    refs: list[str] = []
    budget = MAX_GUIDE_REFERENCE_CHARS
    root = os.path.realpath(code_root) if code_root else ""
    for rel, names in guide["references"]:
        if not root or budget <= 0 or (read_is_denied and read_is_denied(rel)):
            continue
        path = os.path.realpath(os.path.join(root, rel))
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            logger.warning("guide reference missing from the checkout: %s", rel)
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                text = _functions(fh.read(), tuple(names))
        except OSError:
            continue
        if redact:
            text, _ = redact(text)
        if text:
            text = text[:budget]
            budget -= len(text)
            refs.append(f"=== HOW THIS REPO ALREADY FIXES IT (read-only): {rel} ===\n{text}")
    never = "\n".join(f"  - {n}" for n in guide["never"])
    return (f"\nHOW THIS CLASS OF BUG IS FIXED IN THIS REPOSITORY ({rule} in {function})\n"
            f"  What is wrong: {guide['wrong']}\n"
            f"  The fix: {guide['right']}\n"
            f"  Never:\n{never}\n"
            "  Your rewrite is checked with the same rule before it is pushed, and a person reviews the branch.\n"
            "  Follow the shape of the reference below; you may not edit the reference files, so if the component\n"
            "  cannot import them, write the same logic inside the file you are fixing.\n\n"
            + "\n\n".join(refs) + ("\n" if refs else ""))


_SCANNER: Any = None


def _scanner(code_root: str):
    """MOMUS's rule module from the checkout of main, loaded by path (stdlib only)."""
    global _SCANNER
    path = os.path.join(code_root, "momus", "momus", "codescan", "vulnetix_classes.py")
    if _SCANNER is not None and getattr(_SCANNER, "__file__", "") == path:
        return _SCANNER
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("_remediation_vx_rules", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module          # @dataclass looks its module up while the class is built
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    _SCANNER = module
    return module


def still_matches(ticket: dict[str, Any], before: dict[str, str], rewrites: dict[str, str],
                  code_root: str) -> str:
    """The finding's rule run on the rewrite, as MOMUS's gate will run it. "" when the rewrite no longer matches.

    Acceptance marks count only if they were in the file before the patch, as at the gate."""
    rule, function = rule_and_function(ticket)
    if not rule or not code_root:
        return ""
    scanner = _scanner(code_root)
    if scanner is None:
        logger.warning("rule self-check skipped: no MOMUS rule module under %s", code_root)
        return ""
    for rel, new in rewrites.items():
        honored = scanner.ok_marks(before.get(rel, ""))
        for f in scanner.scan_file(rel, new, honored=honored):
            if f.rule == rule and (f.function == function or f.function.endswith("." + function)
                                   or function.endswith("." + f.function)):
                return f"{rel}:{f.line} {f.rule} in {f.function}: {f.message}"
    return ""
