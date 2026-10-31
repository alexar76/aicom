# traits-dev

Private development and staging tree for the YAML/YARA rules consumed by
[cleave](https://github.com/atomdrift-project/cleave). Reviewed releases are
published to the public
[Atomdrift traits repository](https://github.com/atomdrift-project/traits).

End users should install or update traits through cleave rather than cloning
this staging repository:

```bash
cleave update-rules
cleave version
```

## Validation

```bash
make validate                  # reuse unchanged successful validation
make validate-uncached         # fresh fixture analysis
make validate-profile          # uncached phase, fixture, and rule timings
make validate-profile SLOW_RULE_MS=100
```

The performance targets are under 2 seconds cached and under 60 seconds
uncached. Use a release cleave build; the Makefile prefers the sibling
checkout's `target/release/cleave`. Rebuild after changing cleave or its
dependencies so validation exercises the updated engine.

The full-validation cache verifies rule and fixture contents, severity labels,
directory layout, validation settings, and the linked engine's identity on
every run. Changes invalidate it even when file sizes and timestamps stay
the same. Failed or interrupted runs do not populate it. Profiling bypasses
this cache and reports aggregate trait costs, including Tree-sitter queries;
`--verbose` also computes a separate, expensive fixture-overlap diagnostic.
Relative AST cost outliers are confirmed with bounded repeated measurements
on the same input. Real persistent outliers, the original whole-rule time
limit, and query-budget exhaustion remain validation failures.

Every regular file under `testdata/hostile/`, `suspicious/`, `notable/`, or
`baseline/` is a fixture. Its first directory declares its exact highest
finding severity, including archive members and decoded payloads; baseline
allows baseline, component, or no findings. Subdirectories are organizational.
Other files and symlinks under `testdata/` fail validation before rule loading
or cache reuse. Keep notes, scripts, manifests of test expectations, and scan
receipts outside that tree.

Fixtures may occupy at most **500 KiB on disk**. Inputs above **20 KiB** must
use **XZ storage compression**. Files under
`testdata/<severity>/does-nothing/` are exempt from both limits. Validation
removes exactly one final `.xz` storage layer before analysis and preserves
the logical filename; an actual XZ-format sample is stored as `sample.xz.xz`.

Add an input without a shared manifest or overwriting another writer's file:

```bash
scripts/add-fixture /path/to/sample.py testdata/hostile/generated/example/sample.py
make validate
```

The helper applies the storage policy and publishes the complete file
atomically. Choose the expected severity yourself; it does not learn or bless
an observed verdict. See [testdata migration notes](docs/testdata-migration.md)
and [no-op fixture builders](scripts/fixture-builders/does-nothing/README.md).
