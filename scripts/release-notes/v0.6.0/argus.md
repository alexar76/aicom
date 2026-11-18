# ARGUS 0.6.0 — WARDEN 0.30.0, and eSIM purchases that weigh the other sellers

Since 0.5.0 (2026-11-17):

- **WARDEN 0.30.0.** The malware gate checks every package a launch line installs (repeatable npm `--package`, `npm:` aliases, Python launchers' `--with`, `pipx run --spec`), and reading a key after outside text is data, not a key press. Rulesets are unchanged; pins stored by 0.29.0 verify unchanged.
- **No silent switch, no paying above the offer.** When the seller ARGUS ordered an eSIM from refuses the order (nothing charged) and its new price is above the quoted price and above another seller's offer with no less data or days, `esim_buy` buys nothing and answers `cheaper_elsewhere`, naming that offer and the `esim_buy` call for it. The owner approved one seller at one price, so the owner chooses. Otherwise the new price is taken once within the cap, as before.
- The refused seller's new offer replaces its entry in the last offers, so the next `esim_buy` takes the cheapest, and the refused seller, if chosen, is ordered at its new price without a second refusal.
- ARGUS signs no more than the price the owner was shown (or the seller's new offer after a refusal): a seller that issues no quote tokens and asks more than it quoted gets no signature.
- **The Docker image builds again:** the Dockerfile copies `third_party` (the patched `picomatch` override) before npm installs; a test keeps every `file:` dependency copied.

```bash
npm install -g @alexar76/argus3@0.6.0
```

Full list: [CHANGELOG.md](CHANGELOG.md).
