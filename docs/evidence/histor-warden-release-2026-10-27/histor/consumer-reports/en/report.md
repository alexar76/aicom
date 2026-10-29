# Weekly research workflow — synthetic example

Review saved definitions and the checks needed for your workflows.

| Dependency | Result | Workflows to check |
|---|---|---|
| demo:research | Changes observed | 2 |
| demo:migration | Observation conditions changed | 1 |
| demo:offline | Insufficient data | 1 |

## demo:research

**Changes observed**

- Before: 2026\-10\-26T09:00:00Z; package version 1\.0\.0; server version 1\.0\.0; protocol 2025\-06\-18.
- After: 2026\-10\-27T09:00:00Z; package version 1\.1\.0; server version 1\.1\.0; protocol 2025\-06\-18.


### Read archived documents

Retest needed.

- [ ] legacy\_fetch: Check a replacement or pin the previous package; do not run the workflow without review\.

### Prepare the weekly document review

Retest needed.

- [ ] export\_brief: Check action confirmations, permissions and advertised prices; annotations are claims made by the server\.
- [ ] search\_docs: Read the changed instructions; replay a typical request and check tool selection\.
- [ ] search\_docs: Check saved inputs, required fields and types; add a boundary case\.
- [ ] search\_docs: Replay result handling: check the fields and types read by the workflow\.

### Selected tool changes

**export\_brief: Changed**

- destructiveHint: false → true. This is a server claim.
- readOnlyHint: true → false. This is a server claim.

**legacy\_fetch: Removed**


**search\_docs: Changed**

- New required fields: workspace
- Type changes: $/properties/limit, $/properties/workspace
- inputSchema: $\.&quot;properties&quot;\.&quot;limit&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;workspace&quot;\.&quot;type&quot;, $\.&quot;required&quot;\[1\]
- outputSchema: $\.&quot;properties&quot;\.&quot;items&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;results&quot;\.&quot;type&quot;
- Description removed: “using”
- Description added: “in”
- Description removed: “query\.”
- Description added: “selected workspace\. Include source links in the result\.”

Model-facing JSON size in UTF-8: full list 534 → 627 bytes; selected tools 534 → 451 bytes.
These are not tokens or achieved savings.

## demo:migration

**Observation conditions changed**

- Before: 2026\-10\-26T09:00:00Z; package version not applicable; server version 1; protocol 2025\-06\-18.
- After: 2026\-10\-27T09:00:00Z; package version not applicable; server version 2; protocol 2026\-07\-28.

- Changed conditions: protocol; differences cannot be attributed only to a package update.

### Check service status after MCP migration

Comparable observations are needed.

- [ ] Check protocol, launcher and access conditions; repeat both snapshots in the same context\.

### Selected tool changes

No changes were found in the selected definitions.

Model-facing JSON size in UTF-8: full list 94 → 94 bytes; selected tools 94 → 94 bytes.
These are not tokens or achieved savings.

## demo:offline

**Insufficient data**

- Before: 2026\-10\-26T09:00:00Z; package version not applicable; server version 1; protocol 2025\-06\-18.
- After: 2026\-10\-27T09:00:00Z; package version not applicable; server version unknown; protocol unknown.
No successful pair of definitions is available. Tool fields were not compared.

- Limitation: There is no complete successful observation after the update\.

### Get the external service daily status

Comparable observations are needed.

- [ ] Check protocol, launcher and access conditions; repeat both snapshots in the same context\.
- [ ] read\_status: Obtain two complete successful observations in comparable environments\.

### Selected tool changes

**read\_status: Insufficient data**


## Analysis limits

- Only observed definitions are compared, not the server’s runtime behavior\.
- A change does not prove breakage; unchanged definitions do not establish safety\.
- Workflows are linked through explicitly selected tools, without semantic analysis\.
- Compact JSON size in UTF\-8 measures bytes, not tokens, money or achieved savings\.
- launch is represented only by its hash; launch conditions are not executed and environment secrets are not displayed\.

[Full data, versions and input SHA-256 hashes](report.json).
