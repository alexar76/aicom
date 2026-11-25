# Radiolaria N01 implementation-admission fixture

The fixture uses the original playback mock and its `new_code` variant from Radiolaria commit
`cf4840cfde1d64db1a208502c21aa3e8bfbfa716`. The exported snapshots contain the complete native ordered
material, including the exact `source_utf8` strings. The embedded source files retain Radiolaria's
AGPL-3.0 license. [Radiolaria source](https://gitlab.com/radiolaria/radiolaria-os/-/tree/cf4840cfde1d64db1a208502c21aa3e8bfbfa716) · [license](https://gitlab.com/radiolaria/radiolaria-os/-/blob/cf4840cfde1d64db1a208502c21aa3e8bfbfa716/LICENSE)

The JSON also carries a common MCP declaration and application arguments, plus the two corresponding
objects for signing. Its cases map those objects to the native mock tests. The MCP signature and
execution adapter are at the proposal stage. [Binding note](../../mcp-tool-set-digest/notes/implementation-admission.md)

## Checks on 25 November 2026

- Both native snapshots passed Radiolaria's validator. Independent recomputation checked every
  source hash, definition and contract references, implementation reference and admission ID. The
  native encoder and the independent encoder produced identical payload bytes. Changing only the Host
  reference or catalogue revision changed the admission ID.
- Both A and B completed their own authorized mock action, each from a fresh state with exactly one
  executor start. The pinned N01 `new_code` test refused B under A's authorization with
  `capability_invocation_candidate_binding` and zero starts.
- The pinned S08 live admission test rejected a copied admitted object. A fresh observation of the
  original code produced an equal snapshot and the authorized mock action completed.
- The two selected upstream tests passed on Python 3.12.13. The companion repository's
  `scripts/check.sh` also passed with 92 vectors in each of Python, JavaScript and Go.

Run the offline identity check from this directory with `python3 verify_snapshots.py`.
It reads the fixture as data and uses the Python standard library.
