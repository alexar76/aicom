# Orchestration diagnostics

These resolved setup/read retries are separate from product test outcomes. No local project runtime was used.

- A remote-only harness preparation initially checked an escaped newline incorrectly and created no file; its dependent transfer also failed. An inline heredoc corrected the preparation before execution. The final harness stops on any failed stage and gates full tests on focused success.
- One read of Blip's dynamic collection JSON happened while collection was still writing. After completion, both hosts independently reported 1574 cases in 65 files. No source change or test-deadline change resolved that read race.
- One local read-only artifact check used zsh's special `path` variable, temporarily shadowing PATH in that shell. Its subsequent Git metadata check returned 127. A fresh shell reran `git diff --check` successfully; no project code ran locally and no persistent environment changed.
- Product-level pre-fix failures, the initial 50/51 hook pilot with an obsolete Bash mapping expectation, and earlier source snapshots remain in the remote diagnostics. Final acceptance is 1574/1574 and focused 262/262 on each host; those earlier outcomes were not substituted for the final source run.

The final report and source witnesses are unchanged by this explanatory note. Cleanup receipts are under each host's `results/cleanup/`; `owned-containers.remaining.txt` is empty for both.
