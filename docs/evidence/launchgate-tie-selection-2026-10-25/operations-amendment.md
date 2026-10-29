# Operational segmentation, unchanged frozen trial

25 October2026, during the run and before inspecting main selection outcomes.

The published hook helper's frozen study adapter limits a single helper
process to256 sessions. The432-sample plan uses288guarded fresh sessions in
total. To avoid reaching the process-lifetime limit, split execution at the
first completed row count of at least270, well before256guarded sessions.
The only inspected live information is completed-row count and request-ledger
count, not efficacy or answer text. Actual helper bytes, policy, model, payloads,
record-order schedule, repetitions and scorer remain unchanged.

Stop only the experiment runner with SIGTERM. Its owning orchestration waits
for the relay to finish any in-flight request, stops it, and collects the
partial evidence. Preserve every completed row and the original execution
record. Start the exact same frozen experiment command again with a fresh
helper process and the same persistent relay ledger. The existing resume path
skips completed slots and reuses durable slot/stage request IDs and stored
responses for any interrupted slot. Changed request bodies fail closed; an
uncertain previous reservation is not retried.

This is neither a new trial nor additional samples. No failed row is deleted,
no completed answer replaced, and no request budget reset. Verify that the
old JSONL byte prefix is preserved and that the final ledger contains exactly
the scheduled initial calls plus actual Stop follow-ups. The independent
new-study ceiling remains620attempts. Save both segment records and the
operational boundary receipt for the final audit/report.
