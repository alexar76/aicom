Thanks, Kevin. We tested this with a synthetic server and an independent mock-billing ledger, without real payments.

HISTOR's current canary succeeded using `mode: "preview"`: zero mock credits. The same tool with `{}`, or omitted arguments, used its `purchase` default: seven credits. An invalid placeholder failed before billing. Error and timeout controls still incurred the charge.

Matched billed and unbilled servers produced identical MCP messages, excluding timing, while their separate ledgers recorded seven versus zero. A successful preview cannot establish that the default path is free.

Published WARDEN 0.21.0 allowed the call under default wrapping. Marking the tool sensitive required scripted approval for each invocation, but supplied no financial quote.

All 26 scenarios passed across three Linux repeats. This confirms the controlled mechanism; it does not measure census prevalence, Apify's behavior, or real users' awareness.
