# ModelMarket apex Debian security overlay

Build from the running ModelMarket apex image with only the Debian binaries `apt`, `libapt-pkg7.0` and `zlib1g` updated. The package versions address APT CVE-2026-109518 and zlib CVE-2026-27171, CVE-2026-76844 and CVE-2026-85091. [Debian APT tracker](https://security-tracker.debian.org/tracker/CVE-2026-109518) · [Debian zlib advisory](https://lists.debian.org/debian-security-announce/2026/msg00532.html)

`bash fetch.sh` stages the Debian `trixie-security` `InRelease`, `Packages.xz` and three packages under `bundle/`. The image builds with networking disabled. It checks two valid Debian archive signatures with the parent image's installed keyring, the signed release lifetime, both index and package SHA-256 digests and sizes, and each package's identity before `dpkg -i`.

Run `bash debian-rollout.sh prepare` on the Docker host from the staged directory. It checks the exact package delta, Hub source and Python inventory parity, APT/dpkg status, zlib/gzip round trips and both images against disposable snapshots of the production hub and channel SQLite ledgers. It uses the existing scripts under `/root/publisher-custody-20261112` and `/root/hub-3.21.0-rollout-20261112/kit`.

After the active canary's Base transfer reconciles, `bash debian-rollout.sh switch` pauses the payout timer, waits for the current oneshot to exit, snapshots both ledgers, then switches the Hub with both Hub and THEMIS health checks. The timer resumes on exit if it was active before the switch. The container's payout configuration and worker-only signing key placement are inherited. `bash debian-rollout.sh rollback` reverses the image switch using the same timer coordination. The live ledgers and transaction history stay in place.
