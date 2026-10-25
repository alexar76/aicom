# Jakub / KyttoMCP review evidence, 2026-10-25

Research and source changes are local and unreleased. No reply was posted, and no GitHub write was made. AI agents assisted research, code, tests and reporting under the ecosystem owner's direction. Comment reply drafts omit boilerplate at the owner's request.

- [Report](../../growth/jakub-review-check-2026-10-25.ru.md).
- [Clean reply draft](../../growth/jakub-reply-2026-10-25.en.md).
- [Real historical cases](real-cases/README.md): main Mapled change 17172, plus two secondary examples. Registry archives were inspected statically, not installed or executed on macOS.
- [Published WARDEN 0.21.0](published/README.md): 15 behavioral checks passed; a separately recorded wrong package-pin suggestion remains a known defect in that published artifact.
- [Candidate replay](candidate/result.json): 19 checks passed against the final Linux build, including correction of the package-pin advice. [Review text](candidate/rpc-review.txt).
- [Final candidate test run](candidate-final-execution.json): 142 tests in four files passed. Repository global setup also compiled TypeScript. [Log](candidate-final-tests.log).
- [Final source manifest](candidate-final-source-manifest.json) and [compiled module manifest](candidate-final-built-manifest.json): SHA-256 of the local candidate, which is not the published package despite its unchanged package.json version.
- [Cleanup and verification](candidate/cleanup.json): source, compiled modules and downloaded result files checked before removing only the study's temporary directory.

The initial 67-file archive omitted repository setup/config and the own atomic-screen example. Its [failed run](candidate-execution.json) and [log](candidate-tests.log) are preserved. The [retry](candidate-retry-execution.json) restored those inputs and corrected the Python TTY helper; 142 tests passed. The final run additionally checked bounded Unicode metadata and required a specific CAS refusal rather than any helper exception.

All runtime work was on admin-vps, Linux amd64 / Node 22.23.3, Docker **runc**. Dependency preparation downloaded lockfile-pinned development dependencies with lifecycle scripts disabled. Compilation, tests and archived-data replay used no network. Neither Mapled handlers nor KyttoMCP ran in this study. This is review-output and state-transition verification, not a human usability study or a fresh execution census.

Scripts preserve the exact initial/retry/final workflow; replay inputs and outputs include checksums. The hardcoded temporary path in these scripts records this completed run and should not be reused as a new run directory.
