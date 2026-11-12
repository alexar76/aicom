# Warden binary-resource compatibility follow-up

Candidate **0.23.1-dev.20261107.2**, based on the separately retained frozen .1 candidate. Overall acceptance: **true**.

Both gVisor hosts pass304/304 focused tests,1536/1536 tests in63 files, typecheck,build and redteam; source witnesses are unchanged, all commands pass, and no OOM occurred.

The320 source/dist files outside the changed result-screen module are byte-identical to .1: SHA256 5ff407cf78742ae18fd593065e9c9bd552bba45f3fab91f27fae9f45adb13238. Exactly16 declared files differ: result-screen source/compiled maps, existing regression tests, CHANGELOG and version-only metadata. Ruleset19 retains digest sha256-XfRh1+VZoAM6PGtbmqprnSX/eF16qNYOk0o+ilRFxXw=. Full3177-case measurements belong to .1; they were not silently relabelled as .2 measurements. The unchanged definition engine has an additional representative23-case actual-MCP/library check per build on each host: 92/92 cross-host rows match, with zero definition-verdict transitions.

Official SDK1.32.1 interop:8/8 direct/wrapped sessions and4/4 tool-list parity on each host; tool hashes agree across hosts. Separate actual SDK→stdio→wrap checks reproduce the .1 regression: a valid400000-character base64 resource without optional MIME was withheld as incomplete under --results block. The .2 build preserves that blob with or without MIME (blob SHA256 1dd46bf32349db53e130c63c4bc278df83ed2331be4cae06d10b98bd4967b63d). Poisoned metadata, invalid base64 instruction strings with/without MIME, and object-valued blobs are withheld. Every fixture call executes exactly once; refused-result sessions remain usable. Binary-case outcomes agree across hosts.

The first Blip preflight at0.25CPU retained one15s timeout in the large clean-result integration case (153/154). The unchanged code and unchanged test deadlines subsequently pass304/304 and1536/1536 at the normal1CPU profile. The initial23-case helper's template-filename hash receipt is retained; final classifier-pilot-v2 receipts hash the actually executed helper via import.meta.url.

All execution in this follow-up used remote runsc, no network, read-only container roots, unprivileged UID501, dropped capabilities, no-new-privileges, bounded CPU/memory/pids and synthetic fixture data. No upstream malicious implementation or model attack-success experiment ran. This validates the frozen Warden-only candidate; unrelated current-workspace edits are outside this receipt. No local project runtime, GitHub write or npm publication was performed.
