Thanks, jkming — I ran the comparison you suggested. Disclosure: I maintain WARDEN. AI agents prepared the experiments, analysis and this reply under the project owner’s direction.

We compared non-hex windows 6/7/8 with hex fixed at 10, using 960 synthetic credentials and 14,400 attack requests per variant. The complete guard automatically permitted zero attack requests at every threshold: unmatched fragments still stopped for confirmation after credential and outside-text reads. That is separate from recognizing the fragment itself.

Six produced 31 false hard denials in deliberately selected public-text collision controls. Seven had no matches in the new corpus, but we reproduced an older benign JSON/health-text example containing normalized `mit3okt`: denied at seven, allowed at eight. These controls are not production false-positive rates.

So we kept 8/10 and fixed a narrower indexing defect: known provider keys with long alphabetic payloads could lose useful windows before their first digit. The fix moved 717 attack requests from confirmation to denial; those requests were already paused, so they are not newly prevented automatic sends. Ordinary-request decisions stayed unchanged.

The single embedded six-character limitation remains: all 960 such fixtures still required confirmation at eight. The patch is local, unreleased, and undeployed. Measurements ran in networkless Linux Docker containers. Details: https://dev.to/alexar76/we-kept-wardens-810-thresholds-and-fixed-its-credential-index-4khn
