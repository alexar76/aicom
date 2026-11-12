# Histor test correction and accepted scanner validation

Updated `histor/tests/test_observer.py` to match the image manager now installed by `sandbox/install.sh`. The test verifies Dockerfile installation, manager installation, initial rebuild, timer ensure command and timer activation. It runs the actual manager's read-only check mode with a temporary Docker stub, then compares every managed tag with the observer's default/alternate images. Existing Dockerfile checks for git, Java and exclusion of Docker remain.

Validation after the parent installed the accepted Warden0.25.0 archive:

- Observer suite:130passed.
- Focused network/payload/body-budget/CSP/signature/scanner/sink/observer security suite:205passed,9PostgreSQL skips (no test database configured); no deselections or failures.
- Ruff and `git diff --check` passed for the modified test.
- Installed Warden version0.25.0 and dist build digest exactly match vendor metadata: `6c6d85a732825d19e56646b24a679268ae6bf86516fc24cc71ccf31872404a4d`.
- Scanner describe and identity details are retained in adjacent JSON evidence.

Only `histor/tests/test_observer.py` was edited by this subtask. Package/vendor/lock/install work belongs to the parent. No deployment or publishing occurred.
