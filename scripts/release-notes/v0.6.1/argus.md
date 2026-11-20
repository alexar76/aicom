# ARGUS 0.6.1 — WARDEN 0.33.0

Since 0.6.0 (2026-11-18): the WARDEN dependency moves from 0.30.0 to 0.33.0, and ARGUS's built-in list of ecosystem components is refreshed. Nothing else in ARGUS changes.

- **WARDEN 0.32.0's flow-guard change is in.** After outside text, shell code that reads a credential from the environment (`$GH_TOKEN`, `printenv NAME`, `env | curl`, `/proc/<pid>/environ`) is a credential send. ARGUS has no shell tool, so this matters where the same WARDEN package guards an agent as a hook or plugin.
- 0.31.0 and 0.33.0 add the OpenWebUI set-up command and checks of Open Terminal calls through the gateway: modules ARGUS does not load.
- Rulesets (23), the known-malicious package list and scan verdicts are as in 0.30.0. Pins stored by WARDEN 0.30.0 verify under 0.33.0, so servers approved before the update stay approved.

```bash
npm install -g @alexar76/argus3@0.6.1
```
