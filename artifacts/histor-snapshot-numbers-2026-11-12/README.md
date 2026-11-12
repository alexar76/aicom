# Two numbers from HISTOR snapshot 2026-11-02, for the Security IG post

Computed 2026-11-12 by `ds_numbers.py` from https://histor.modelmarket.dev/datasets/2026-11-02/
(`changes.jsonl.gz`, `extras_changes.jsonl.gz`, `servers.jsonl.gz`). Their SHA-256 equal the signed
`manifest-2026-11-02.json` (printed at the top of `output-2026-11-02.txt`). Version DOI of that snapshot:
https://doi.org/10.5281/zenodo.23884408 . Changes recorded 2026-09-24T10:53:44Z … 2026-11-02T07:19:57Z.

Run: `python3 ds_numbers.py <folder with the three files and manifest.json>`.

Counted per **host** for remote servers: one host (gateway.pipeworx.io) alone holds 31.2% of all remote changes,
so a per-change share would describe that host.

- 27,947 remote hosts in the snapshot; 7,112 changed a tool definition at least once (name, description,
  inputSchema, outputSchema: the MTL/1 digest).
- **5,714 of the 7,112 (80.3%)** made at least one such change while the version the server reports about itself
  (`serverInfo.version`, recorded on both sides of the change) stayed the same.
- **2,799 of the 7,112 (39.4%)** had at least one change in which only tool descriptions moved: no tool added or
  removed, no schema changed. That is the text a model reads.

Limits, from the snapshot's README: one anonymous client on one host; polling can miss states between reads; a
list that differs per session shows up as changes alternating between two digests; a change is not a judgement.
Packages (npm/PyPI, read once per published version) are counted separately in the output and not used in the post.
