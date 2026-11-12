# ARD article quality work — 2026-11-08

Article and rendered assets remain in the authorized PromoMaterials pack:
`../PromoMaterials/devto/ard-six-hubs-2026-11-07/` (relative to aicom).

## Technical reproduction

- `reproduce_binding.py` reads only the public modelmarket.dev manifest, registry search,
  DID document and descriptor. It verifies the selected local publisher, Ed25519 JWS,
  full signed-subject equality and raw-descriptor SHA-256 digest.
- The controlled change deletes only the outer result's version in memory. The unchanged
  inner trustManifest still verifies and the descriptor digest still matches; subject
  equality fails. `binding-check.json` records the observed result and time, and
  `public-signed-result.json` is the public input.
- Canonical serialization in this evidence script deliberately supports only JSON objects
  and ASCII-string leaves. Other JSON values are refused. It is not a general RFC 8785
  implementation or a recommended production verifier.
- `article-binding-snippet.sh` contains the exact added article code (plus the registry
  variable supplied by earlier article steps); it ran successfully and printed
  `snippet-output.txt`. This smaller snippet isolates subject equality only.

## Figures and QA

- `make_figures.py` writes SVG primitives and renders the same primitives through Pillow,
  antialiased at 2x, into the pack's `assets-v2/` directory.
- `ard-discovery-boundary`: 1600×1000, showing origin → manifest → registry → descriptor,
  with the separate v2 invoke boundary. `ard-subject-binding`: 1600×1050, showing the
  controlled version omission and the different outcomes of the three checks.
- Both images were opened for visual inspection; one overflowing origin label was fixed
  and the figure inspected again. Labels are at least 26px. Text bounds are retained here.
- `local-qa.json` records dimensions, hashes and preservation of frontmatter and all four
  original curl code blocks. Before-image is `article.before-quality-2026-11-08.md` in
  the promo pack. Final body: 866 → 1087 whitespace-separated words, including code and captions.

No paid capability invocation, authenticated API call, GitHub write, DEV.to edit, blog
deployment, cover edit or change to another article was performed by this work.
