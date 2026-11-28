"""patch_text.py PACKAGE_DIR [--check] — hub 3.22.5's public-text change over a running hub's own code.

Public texts say "Agent Capital Exchange", never the acronym (owner, 2026-11-15). The hub's /openapi.json still had
the tag `acex-capital` and two descriptions with the acronym; two 503 bodies had it too. Every replacement below must
match exactly once in the running file, else nothing is written and the script exits 3. --check only reports.
"""
import pathlib
import sys

EDITS = {
    "hub_routes/capital.py": [
        ('"""ACEX capital: pricing, Agent IPO', '"""Agent Capital Exchange: pricing, Agent IPO'),
        ('"""Capability revenue indices for Pulse Terminal (ACEX Phase 2)."""',
         '"""Capability revenue indices for Pulse Terminal (Agent Capital Exchange, phase 2)."""'),
        ('tags=["acex-capital"]', 'tags=["capital"]'),
        ('"""The 503 for a public ACEX read whose ledger cannot be opened.',
         '"""The 503 for a public Agent Capital Exchange read whose ledger cannot be opened.'),
        ('"detail": f"the ACEX {ledger} ledger is not available on this hub",',
         '"detail": f"the Agent Capital Exchange {ledger} ledger is not available on this hub",'),
    ],
    "api_models.py": [
        ('"""Float a product as an ACEX CapShares listing (Agent IPO)."""',
         '"""Float a product as an Agent Capital Exchange CapShares listing (Agent IPO)."""'),
    ],
    "capital_pricing.py": [
        ('"""Hub capital pricing for Pulse Terminal (ACEX Phase 2)."""',
         '"""Hub capital pricing for Pulse Terminal (Agent Capital Exchange, phase 2)."""'),
        ('"ACEX capital pricing is unavailable: the `acex` package is not importable. "',
         '"Agent Capital Exchange pricing is unavailable: the `acex` package is not importable. "'),
    ],
}


def main() -> int:
    root = pathlib.Path(sys.argv[1])
    check = "--check" in sys.argv[2:]
    out, bad = {}, []
    for rel, pairs in EDITS.items():
        p = root / rel
        s = p.read_text(encoding="utf-8")
        for old, new in pairs:
            n = s.count(old)
            if n != 1:
                bad.append(f"{rel}: {n} x {old[:60]!r}")
            s = s.replace(old, new)
        out[p] = s
    if bad:
        print("NOT APPLIED\n  " + "\n  ".join(bad))
        return 3
    if check:
        print("ok: all", sum(len(v) for v in EDITS.values()), "replacements match once")
        return 0
    for p, s in out.items():
        p.write_text(s, encoding="utf-8")
    print("applied", sum(len(v) for v in EDITS.values()), "replacements in", len(out), "files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
