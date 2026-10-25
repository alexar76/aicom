# WARDEN 0.20.0 — closed as far as it goes without false positives, and one false positive of 0.19.0 fixed

```bash
npx -y @aimarket/warden@0.20.0 scan
```

0.19.0 closed 11 of the 14 code-aware attacks that got through the flow guard. This release goes after what was left, adds six attacks against the new rules, and keeps only what a measurement says costs no false positive. 2 of the 23 attacks get through, both named in the docs.

- **A false positive in 0.19.0, fixed.** After a session read an RSA private key, 0.19.0 denied sending a README that holds a DKIM public key, as "part of a credential": every DER key shares its algorithm identifier. Parts every key of a kind shares (DER headers and algorithm identifiers, a JWT's header and claims) are no longer fingerprinted.
- **Key windows are measured, not chosen.** 480 made-up keys in eight formats against 115 million letters and digits of ordinary text: 0.19.0's rules matched by chance 19 times, 0.20.0's (8 letters and digits, 10 for hex keys) 0 times. Pieces of 8 characters wrapped in other words are now denied.
- **A key read in the session written into an ordinary project file asks** after outside text. `.env` and the other credential files still pass.
- **An address only in pasted or quoted text is not one you named**: sending to it asks once. A full stop after an address you typed no longer hides it.
- **Answers that repeat an instruction aimed at the model go back once** to be checked (Stop hook). On a model that follows AgentDojo's answer-only attack, the guard's note had already taken it from 6 of 20 answers to 0; the re-check is a safety net, and the docs say so.
- **`wrap` now enforces `sensitiveToolPatterns`.** Before, it accepted the patterns and did not enforce them. Each call to a matching tool now waits for a person, asked through the client's MCP elicitation form; a client without one gets a refusal, and the server never receives the call.
- **Ruleset v16:** MCPTox's held-out half 194 → 210 of 218 poisoned tools, with no new block on 45 clean servers, 999 public servers or 1,000 npm/PyPI packages.

Still open, in the docs: pieces under 8 characters dressed as ordinary sentences, a key spelled out in words, and an answer-only injection the guard does not recognise as an instruction. [What the flow guard does not do](https://github.com/alexar76/warden/blob/main/docs/flow-guard.md#what-it-does-not-do).

Full list: [CHANGELOG.md](https://github.com/alexar76/warden/blob/main/CHANGELOG.md).
