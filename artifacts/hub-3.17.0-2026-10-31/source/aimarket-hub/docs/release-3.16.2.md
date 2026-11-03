# aimarket-hub 3.16.2

The counterparty-check workflow can opt into `continue_on_error` when running
trial nodes through Studio. The request field is a strict boolean and is
forwarded to the configured executor only when enabled.

Paid Studio run responses now include each step's result and provider receipt
behind the run token. Public bills of materials contain the result's SHA-256
commitment without copying source data into the signed bill. Failed provider
responses retain their evidence too.

Provider-auth documentation and its fixture use the new SYMMARTYS name.

This version separates these changes from the already published 3.16.1
artifacts. The provenance plugin keeps its independent version, 2.3.1.
