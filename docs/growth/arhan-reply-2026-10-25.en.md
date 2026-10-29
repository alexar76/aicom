Thanks, Arhan — I’ve now checked the full before/after tool lists in the same frozen October 20 snapshot.

Of the original **2,036 servers**, **1,994** had at least one observed tool-description edit beyond digits and whitespace. For **39**, the observed tool-description edits were only numeric, allowing whitespace changes; for **3**, only whitespace changed. Those categories describe the descriptions, not everything else in the interface.

The event denominator is **5,482 description-touching transitions**: **5,014** included text changes beyond digits/whitespace, **462** were numeric in that part, and **6** were whitespace-only. With both schemas and tool membership exactly unchanged, **372** transitions changed only numbers, possibly with whitespace, and **5** changed only whitespace in the top-level descriptions. Across the entire observed history, **27 servers** meet that stricter numeric-only interface criterion; another **2** meet its whitespace-only counterpart.

There’s a useful counterexample to treating numeric edits as automatically harmless: [change #13185](https://histor.modelmarket.dev/api/v1/changes/13185) changes the advertised per-call price from **$0.002 to $0.02**, without changing the schema. That is a description observation, not a billing test. I’m keeping the literal trust digest; the number-masked view is a review aid.

I also counted schema and tool-membership changes separately, preserving overlaps. The cohort has 7,319 total transitions; 12 lack full raw states and remain unknown for text/schema classification. All 5,482 description transitions above have both states available. This is a reanalysis of the original snapshot, not a new capture or a harmful-change rate.
