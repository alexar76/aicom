# Tool-list changes that break a prompt cache without changing meaning (week of 2026-10-25)

Asked by a dev.to comment (Paul Irolla, Tokenade, 2026-11-01): a changed byte in the tool list breaks the prompt
cache. `cachechurn.py` classifies every HISTOR change between 2026-10-25 and 2026-11-01 with both tool lists stored.
It compares tool by tool, in steps:
1. whitespace collapsed;
2. dates and timestamps blanked;
3. version strings blanked;
4. every number blanked.

The step at which the two lists become equal names the change.

Published at https://histor.modelmarket.dev/datasets/cache-churn-2026-11-01/. License: CC BY 4.0.

It reads HISTOR's database read-only. Run it in a throw-away container from the service image, as HISTOR's export
does, not inside the live service (its blob cache needs more memory than the service is given):

    docker run --rm -i --user 65532:65532 --read-only --tmpfs /tmp --memory 768m --network histor_default \
      --env-file <HISTOR_PROFILE, HISTOR_DATABASE_URL, HISTOR_DATA_DIR, HISTOR_OPERATOR_TOKEN, HISTOR_PUBLIC_BASE> \
      -v histor_histor-data:/data:ro -e PYTHONPATH=/app --entrypoint python <image> - < cachechurn.py

Result: `result.json`.
- 10,712 changes on 4,491 servers.
- 331 changes on 27 servers changed only a date or a timestamp. One server made 237 of them (fork.zone, a
  `whats_new` description that carries the time it last read its feed); the other 26 made 94.
- 134 more changed only a decimal number. Despite the label `only dates and version strings` in `result.json`, the
  step-3 pattern (`\bv?\d+(\.\d+)+`) also blanks prices: by `examples.py`, about 126 of the 134 are prices or
  metered averages in a description (37 servers; one went from $1.00 to $222.00), 5 are version strings, 3 other.
  A price change is a real change for an agent that pays, so these do not belong with "no change in meaning".
- 657 changed only numbers. These are ambiguous: counts, but also real limits.
- 218 servers changed 7 or more times, 3,661 changes, a third.

Reordering is not counted, because HISTOR's digest sorts tools and keys.

**Examples** (`examples.py`, output `examples.json`, same week, same throw-away container): per server, the changes
of the two classes above, the fields that moved, one before/after snippet and the size of the tool list. Of 2,119
field differences, 1,963 are in tool descriptions and 156 in input schemas (defaults, examples, property
descriptions). Kinds seen: "Today is <date>" or "Current date is <date>" written for the model; "as of", "measured",
"indexed on", "prices verified" dates; booking examples one day ahead; `default` values set to the server's start
time.

## Cite

Artamokhov, A. (2026). Tool-list changes that break a prompt cache without changing meaning, week of 25 Oct 2026.
HISTOR. https://histor.modelmarket.dev/datasets/cache-churn-2026-11-01/
