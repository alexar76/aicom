# Publisher custody deployment security checks

The exact modelmarket.dev candidate `sha256:7c41749d850ce4569cf755570fc8bf8de97f563ffdd7ff13cc8f74d36acef9e8` was inspected in an ephemeral container with networking disabled and no mounted service data. Its Python 3.12.15 package inventory (76 distributions) and Debian trixie inventory (133 binary packages from 94 sources) match the prior active image `0d2aeefc891c` exactly. After the switch, the active image matched the candidate and reported healthy with zero restarts. [Package parity](candidate-inventory-parity.json) · [Active image check](active-image.json)

| Source | Scope | Result |
| --- | --- | --- |
| Vulnetix | 17,976 published records from the PyPI, VULN-PYPI and OSM families, immutable commit `5f0afbd5a343a1dbc5571574e2d4e3c610be14e8` | 0 affected Python package matches and 0 version-matching errors |
| OSV | 26,231 active PyPI records, including 6,594 GHSA and 7,631 PYSEC records | 0 affected Python package matches and 0 version-matching errors |
| CISA KEV | 1,779 known-exploited entries checked against affected advisory IDs | 0 overlaps |
| Debian Security Tracker | 1,887 trixie records scoped to installed source packages, including 835 unique version comparisons with `dpkg` | 0 high/critical under Debian's assigned urgency and 0 CISA KEV matches. 145 affected records have unassigned urgency, 54 are marked unimportant, and 4 remain undetermined |

The inherited Debian packages fall below four published fixed-version thresholds. Debian's trixie updates fix `apt` CVE-2026-109518 in `3.0.4` and three `zlib` advisories in `1:1.3.dfsg+really1.3.1-1+deb13u1`. The APT advisory concerns on-path manipulation of package downloads during an install or update. The package set is identical in the two images. The Debian comparison preserves every raw affected or undetermined entry and does not establish application-level reachability. [Debian findings](debian-results.json) · [APT advisory](https://www.debian.org/security/2026/dsa-6607) · [zlib advisory](https://www.debian.org/security/2026/dsa-6613)

Scoped Bandit source inspection found nine alerts already in the baseline and one new B608 alert. The new alert covers a SQL predicate selected from two fixed literals; the row limit remains a bound parameter. The reviewed code has zero high-severity Bandit alerts. [Raw Bandit results](bandit.json) · [Baseline comparison](static-review.json)

The advisory result includes the hashes of the downloaded databases and the Vulnetix snapshot. Published data was downloaded by read-only requests and matched locally. Package inventories and repository source were not sent to external databases. Python advisory coverage applies to the recorded package distributions; Debian coverage applies to installed `.deb` metadata. Neither scan covers the host, the container platform or source code reachability. [Advisory results](advisory-results.json) · [Matcher](match.py)
