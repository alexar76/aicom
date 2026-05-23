# Security Policy — AI Market Hub

## Reporting a Vulnerability

**DO NOT open a public issue.** Send to `security@aicom.io` (PGP below).

Response within 24 hours. Full disclosure after fix + 30 days.

## Bug Bounty

Launching with mainnet on Immunefi. See `contracts/audits/PAYMENT_LAYER_SECURITY_AUDIT.md` for detailed findings.

### Scope & Rewards (when funded, pool target $250k)

| Severity | Reward | Example |
|---|---|---|
| Critical | $50k–$250k | Direct theft of escrowed funds, signature forgery |
| High | $10k–$50k | Channel hijacking, replay bypass, safety gate bypass |
| Medium | $2k–$10k | DoS on channels, balance inconsistency |
| Low | $500–$2k | Edge case with no fund loss |

### Out of Scope
- Attacks requiring multisig key compromise
- Known issues in the internal audit

## Audit Reports

| Date | Firm | Scope | Report |
|---|---|---|---|
| 2026-05 | Internal | Payment channels, contracts, signing | `contracts/audits/` |
| TBD | External #1 | Full | Coming |
| TBD | External #2 | Contracts | Coming |

## PGP

Email `security@aicom.io` for PGP key. Key fingerprint published on request.
Do not include sensitive details in the initial email — we will provide the PGP key for encrypted follow-up.
