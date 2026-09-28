#!/usr/bin/env python3
"""Ecosystem parity guard for aimarket-protocol + aimarket-sdks.

These two directories are developed inside this monorepo and published as
independent GitHub satellites (alexar76/aimarket-protocol, alexar76/aimarket-sdks).
Their cross-language correctness is *not* guaranteed by any one satellite's CI —
each ships on its own. This guard runs in the monorepo (the source of truth) and
makes the three classes of drift impossible to merge:

  1. Version skew  — the three SDK packages (Dart / TS / Rust) must ship the
     same package version. The README literally advertises one number for all
     three ("SDK package version: X (Dart / TS / Rust)").

  2. Model skew    — the protocol data models must exist in all three SDKs with
     the same field count. Naming differs by language convention (snake_case in
     TS/Rust, camelCase in Dart, and `Capability.id` vs `capability_id`), so we
     compare *field counts per model*, which catches the dominant failure mode:
     "added a field to one SDK, forgot the others."

  3. Vector skew   — the cross-SDK signing fixture is a single source of truth.
     Its committed digest sidecar must match the fixture, and the language test
     suites must bind to that one fixture (not fork their own copy).

  4. Method skew   — the AimarketAgent class must expose the same public methods
     in all three SDKs. Here names ARE compared (after camelCase → snake_case),
     because a method is found by name: models matched on field count alone let
     the Rust agent ship without fetch_trusted_hashes and verify_tee_receipt
     while both other SDKs had them, and the guard still said PARITY OK.
     Module-level helpers outside the class (TypeScript's `market`) are not
     covered.

This is deliberately a *guard*, not a code generator: the SDK models are hand-
tuned for each language's ergonomics (BigInt/viem in TS, serde in Rust,
web3dart in Dart) and generating them would regress DX. The guard locks the
invariants that matter without owning the code.

Exit code 0 = parity holds. Non-zero = a hard invariant was violated.
Run from anywhere; paths are resolved relative to the repo root.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = REPO_ROOT / "aimarket-protocol"
SDKS = REPO_ROOT / "aimarket-sdks"

# The canonical protocol data models. Every SDK must expose each of these with
# a matching field count. Edit this list when the protocol gains/loses a model.
CANONICAL_MODELS = [
    "Capability",
    "Channel",
    "InvokeResult",
    "TeeAttestation",
    "TeeReceipt",
    "PlanStep",
    "Settlement",
    "BillOfMaterials",
    "SearchResponse",
]

# The public AimarketAgent surface, in snake_case. Every SDK must expose each of these,
# and nothing public beyond them except what LANGUAGE_ONLY allows. Edit this list when
# the agent gains or loses a method — in all three SDKs.
CANONICAL_AGENT_METHODS = [
    "well_known", "discover", "discover_product",
    "open_channel", "get_channel_balance", "invoke", "invoke_batch", "close_channel",
    "verify_tee_attestation", "verify_tee_receipt", "trust_code_hash", "fetch_trusted_hashes",
    "run_once", "dispose",
]
# Public methods that exist in one language by its conventions, not as protocol surface.
LANGUAGE_ONLY = {
    "rust": {"new", "with_config"},     # constructors are associated functions in Rust
    "ts": set(),
    "dart": set(),
}

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def _c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}" if sys.stdout.isatty() else text


def _balanced_block(text: str, open_idx: int, opener: str = "{", closer: str = "}") -> str:
    """Return the substring from the opener at/after open_idx to its match."""
    start = text.index(opener, open_idx)
    depth = 0
    for i in range(start, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unbalanced block")


# ---------------------------------------------------------------------------
# Field-count extraction per language
# ---------------------------------------------------------------------------

def ts_field_count(src: str, model: str) -> int | None:
    m = re.search(rf"\binterface\s+{model}\s*\{{", src)
    if not m:
        return None
    body = _balanced_block(src, m.start())
    # `name: type;` / `name?: type;` — interfaces here carry only fields.
    return len(re.findall(r"^\s*[A-Za-z_]\w*\??\s*:", body, re.MULTILINE))


def rust_field_count(src: str, model: str) -> int | None:
    m = re.search(rf"\bstruct\s+{model}\s*\{{", src)
    if not m:
        return None
    body = _balanced_block(src, m.start())
    # `pub field: Type,` — the `pub` prefix distinguishes fields from #[serde] attrs.
    return len(re.findall(r"^\s*pub\s+\w+\s*:", body, re.MULTILINE))


def dart_field_count(src: str, model: str) -> int | None:
    m = re.search(rf"\bclass\s+{model}\b", src)
    if not m:
        return None
    # Count `this.field` in the generative `const Model({ ... })` constructor.
    ctor = re.search(rf"\b{model}\s*\(", src[m.start():])
    if not ctor:
        return None
    params = _balanced_block(src[m.start():], ctor.start(), "(", ")")
    return len(re.findall(r"\bthis\.\w+", params))


# ---------------------------------------------------------------------------
# Version extraction per package
# ---------------------------------------------------------------------------

def dart_version() -> str | None:
    text = (SDKS / "dart" / "pubspec.yaml").read_text()
    m = re.search(r"^version:\s*(\S+)", text, re.MULTILINE)
    return m.group(1) if m else None


def ts_version() -> str | None:
    return json.loads((SDKS / "typescript" / "package.json").read_text()).get("version")


def rust_version() -> str | None:
    text = (SDKS / "rust" / "Cargo.toml").read_text()
    # First `version = "..."` (under [package]).
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_versions(failures: list[str]) -> None:
    print(_c(YELLOW, "▌ 1. SDK package version parity"))
    versions = {"dart": dart_version(), "ts": ts_version(), "rust": rust_version()}
    proto = (PROTOCOL / "VERSION").read_text().strip()
    distinct = set(versions.values())
    for lang, v in versions.items():
        print(f"    {lang:<6} {v}")
    print(f"    {DIM if sys.stdout.isatty() else ''}protocol spec: {proto}{RESET if sys.stdout.isatty() else ''}")
    if None in distinct:
        failures.append("could not read one of the SDK versions")
        print(_c(RED, "    ✗ missing version"))
    elif len(distinct) != 1:
        failures.append(f"SDK versions diverge: {versions}")
        print(_c(RED, "    ✗ versions diverge"))
    else:
        print(_c(GREEN, f"    ✓ all three SDKs at {distinct.pop()}"))


def check_models(failures: list[str]) -> None:
    print(_c(YELLOW, "\n▌ 2. Cross-language model parity"))
    ts_src = (SDKS / "typescript" / "src" / "models.ts").read_text()
    rust_src = (SDKS / "rust" / "src" / "models.rs").read_text()
    dart_src = (SDKS / "dart" / "lib" / "src" / "models.dart").read_text()

    print(f"    {'model':<18}{'ts':>5}{'rust':>6}{'dart':>6}")
    for model in CANONICAL_MODELS:
        counts = {
            "ts": ts_field_count(ts_src, model),
            "rust": rust_field_count(rust_src, model),
            "dart": dart_field_count(dart_src, model),
        }
        missing = [lang for lang, c in counts.items() if c is None]
        present = {lang: c for lang, c in counts.items() if c is not None}
        ok = not missing and len(set(present.values())) == 1
        mark = _c(GREEN, "✓") if ok else _c(RED, "✗")
        cells = f"{('-' if counts['ts'] is None else counts['ts']):>5}{('-' if counts['rust'] is None else counts['rust']):>6}{('-' if counts['dart'] is None else counts['dart']):>6}"
        print(f"  {mark} {model:<18}{cells}")
        if missing:
            failures.append(f"model {model} missing in: {', '.join(missing)}")
        elif len(set(present.values())) != 1:
            failures.append(f"model {model} field-count mismatch: {present}")


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def rust_agent_methods(src: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"^impl AimarketAgent\s*\{", src, re.MULTILINE):
        names |= set(re.findall(r"^    pub (?:async )?fn (\w+)", _balanced_block(src, m.start()), re.MULTILINE))
    return names


def ts_agent_methods(src: str) -> set[str]:
    m = re.search(r"export class AimarketAgent\b", src)
    if not m:
        return set()
    body = _balanced_block(src, m.start())
    public = set(re.findall(r"^  (?:async )?(?:get )?([a-zA-Z]\w*)\s*\(", body, re.MULTILINE))
    hidden = set(re.findall(r"^  (?:private|protected) (?:async )?([a-zA-Z]\w*)\s*\(", body, re.MULTILINE))
    return {_snake(n) for n in public - hidden - {"constructor"}}


_DART_TYPE = r"(?:Future<[^\n(]*?>|Stream<[^\n(]*?>|[A-Z]\w*(?:<[^\n(]*?>)?\??|void|bool|int|double|num|String|dynamic)"


def dart_agent_methods(src: str) -> set[str]:
    m = re.search(r"class AimarketAgent\b", src)
    if not m:
        return set()
    body = _balanced_block(src, m.start())
    # A member at class indent with a return type; `_private` names are not public.
    found = re.findall(
        rf"^  (?:static\s+)?{_DART_TYPE}\s+(?:get\s+)?([a-z]\w*)\s*(?:\(|<|async\b|\{{|=>)",
        body, re.MULTILINE)
    return {_snake(n) for n in found}


def check_methods(failures: list[str]) -> None:
    print(_c(YELLOW, "\n▌ 4. Agent method parity"))
    found = {
        "ts": ts_agent_methods((SDKS / "typescript" / "src" / "agent.ts").read_text()),
        "rust": rust_agent_methods((SDKS / "rust" / "src" / "agent.rs").read_text()),
        "dart": dart_agent_methods((SDKS / "dart" / "lib" / "src" / "agent.dart").read_text()),
    }
    print(f"    {'method':<26}{'ts':>5}{'rust':>6}{'dart':>6}")
    for method in CANONICAL_AGENT_METHODS:
        have = {lang: method in names for lang, names in found.items()}
        mark = _c(GREEN, "✓") if all(have.values()) else _c(RED, "✗")
        cells = "".join(f"{('✓' if have[lang] else '-'):>{w}}" for lang, w in (("ts", 5), ("rust", 6), ("dart", 6)))
        print(f"  {mark} {method:<26}{cells}")
        missing = [lang for lang, ok in have.items() if not ok]
        if missing:
            failures.append(f"agent method {method} missing in: {', '.join(missing)}")
    for lang, names in found.items():
        extra = sorted(names - set(CANONICAL_AGENT_METHODS) - LANGUAGE_ONLY[lang])
        if extra:
            print(f"  {_c(RED, '✗')} {lang} has public methods the others lack: {', '.join(extra)}")
            failures.append(f"{lang} agent methods not in CANONICAL_AGENT_METHODS: {', '.join(extra)}")


def check_vectors(failures: list[str]) -> None:
    print(_c(YELLOW, "\n▌ 3. Cross-SDK test-vector integrity"))
    vec_path = SDKS / "test-vectors" / "debit_authorization.json"
    dig_path = SDKS / "test-vectors" / "debit_authorization.digest"
    vec = json.loads(vec_path.read_text())

    required_keys = {"params", "canonicalMessage", "ed25519SeedHex",
                     "ethereumPrivateKeyHex", "expectedDigest"}
    missing_keys = required_keys - set(vec)
    if missing_keys:
        failures.append(f"fixture missing keys: {sorted(missing_keys)}")
        print(_c(RED, f"    ✗ fixture missing keys: {sorted(missing_keys)}"))
    else:
        print(_c(GREEN, "    ✓ fixture has all required keys"))

    sidecar = dig_path.read_text().strip().removeprefix("0x")
    expected = str(vec.get("expectedDigest", "")).strip().removeprefix("0x")
    if sidecar == expected and sidecar:
        print(_c(GREEN, f"    ✓ digest sidecar matches fixture ({sidecar[:12]}…)"))
    else:
        failures.append("digest sidecar != fixture expectedDigest")
        print(_c(RED, f"    ✗ digest mismatch: sidecar={sidecar[:12]}… fixture={expected[:12]}…"))

    # Which language suites bind to the single shared fixture?
    # A LIST per language: the binding test may live in the language's conventional
    # cross-SDK file or in its main suite, and pinning one path made a real binding read
    # as "not yet cross-checked" simply because it was added next door.
    binders = {
        "ts": [SDKS / "typescript" / "test" / "cross_sdk_vectors.test.ts"],
        "rust": [SDKS / "rust" / "tests" / "cross_sdk_vectors.rs"],
        "dart": [
            SDKS / "dart" / "test" / "cross_sdk_vectors_test.dart",
            SDKS / "dart" / "test" / "aimarket_agent_test.dart",
        ],
    }
    bound = [
        lang
        for lang, paths in binders.items()
        if any(p.exists() and "test-vectors/debit_authorization" in p.read_text()
               for p in paths)
    ]
    print(f"    bound to shared fixture: {', '.join(bound) if bound else 'none'}")
    if len(bound) < 2:
        failures.append(f"fewer than 2 SDKs bind to the shared fixture: {bound}")
        print(_c(RED, "    ✗ shared fixture under-used"))
    else:
        unbound = [l for l in binders if l not in bound]
        if unbound:
            print(_c(YELLOW, f"    ⚠ not yet cross-checked (informational): {', '.join(unbound)}"))


def main() -> int:
    print(_c(YELLOW, "AIMarket ecosystem parity guard"))
    print(f"{DIM if sys.stdout.isatty() else ''}repo: {REPO_ROOT}{RESET if sys.stdout.isatty() else ''}\n")
    failures: list[str] = []
    check_versions(failures)
    check_models(failures)
    check_vectors(failures)
    check_methods(failures)

    print()
    if failures:
        print(_c(RED, f"PARITY BROKEN — {len(failures)} issue(s):"))
        for f in failures:
            print(_c(RED, f"  • {f}"))
        return 1
    print(_c(GREEN, "PARITY OK — protocol and all three SDKs are consistent."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
