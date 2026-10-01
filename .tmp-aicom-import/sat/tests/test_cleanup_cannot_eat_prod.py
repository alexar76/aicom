"""The disk cleanup must not be able to delete a stopped service's image.

**What happened.** `scripts/ecosystem_process_cleanup.sh` stopped the Alien Monitor stack
(`docker compose -f alien-monitor/docker-compose.prod.yml down --remove-orphans`) and then, at the
end of the same script, ran `scripts/disk_cleanup.sh` — which did `docker system prune -af`.

`-a` removes every *tagged* image that no *running* container references. The monitor had just
been stopped, so its image qualified. The deploy did not finish rebuilding it and the factory host
was left with neither container nor image: `monitor.modelmarket.dev/` returned 502 until it
was rebuilt from source, ten minutes of Docker build on a 7 GB box with no rollback available.

`disk_cleanup.sh` also runs from cron, so this was never specific to a deploy: any service that
happened to be down when the timer fired was one prune away from the same outcome.

**Both halves are asserted here** because either alone fixes this instance and neither alone fixes
the class. Ordering protects this script's own stops; dropping `-a` protects every other caller,
including cron. Dropping `-a` costs almost nothing: an image superseded by a rebuild of the same
tag becomes dangling, and plain `prune -f` still collects dangling images.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEANUP = ROOT / "scripts" / "ecosystem_process_cleanup.sh"
DISK = ROOT / "scripts" / "disk_cleanup.sh"


def _live_lines(path: Path) -> list[tuple[int, str]]:
    """Numbered lines with comments stripped — a rule documented in a comment is not a rule."""
    out = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if re.match(r"\s*#", raw):
            continue
        out.append((lineno, raw.split("#", 1)[0]))
    return out


def test_system_prune_does_not_take_all_images() -> None:
    offenders = [
        f"disk_cleanup.sh:{n}: {ln.strip()}"
        for n, ln in _live_lines(DISK)
        if re.search(r"docker\s+system\s+prune\b[^|;]*\s-\w*a", ln)
    ]
    assert not offenders, (
        "`docker system prune -a` deletes the last good image of every STOPPED service — the "
        "rollback, not the garbage. It cost us the production Alien Monitor.\n  "
        + "\n  ".join(offenders)
        + "\n\nUse `docker system prune -f`. For real space, `docker builder prune -af` is "
          "already there and the build cache is where the gigabytes are.")


def test_image_prune_does_not_take_all_images() -> None:
    """Same rule, the other spelling: `docker image prune -a` is `system prune -a` for images."""
    offenders = [
        f"disk_cleanup.sh:{n}: {ln.strip()}"
        for n, ln in _live_lines(DISK)
        if re.search(r"docker\s+image\s+prune\b[^|;]*\s-\w*a", ln)
    ]
    assert not offenders, "`docker image prune -a` has the same effect:\n  " + "\n  ".join(offenders)


def test_builder_prune_is_still_aggressive() -> None:
    """The counterpart. Build cache IS disposable, and if someone 'fixes' this file by softening
    the builder prune too, the disk fills up and the -a comes back."""
    text = DISK.read_text(encoding="utf-8")
    assert re.search(r"docker\s+builder\s+prune\s+-\w*a", text), (
        "docker builder prune lost its -a. That is the prune that should be aggressive; "
        "weakening it is what creates pressure to re-add -a to the image prune.")


def test_disk_cleanup_runs_before_anything_is_stopped() -> None:
    """Ordering: prune while everything is still running, so no service is ever a prune candidate
    merely because this script stopped it a moment ago."""
    lines = _live_lines(CLEANUP)
    prune_at = [n for n, ln in lines if "disk_cleanup.sh" in ln and "-x" not in ln]
    stop_at = [n for n, ln in lines if re.search(r"compose\b.*\bdown\b", ln)]

    assert prune_at, "ecosystem_process_cleanup.sh no longer calls disk_cleanup.sh"
    assert stop_at, "no `compose … down` found — if the stops are gone, delete this test"
    assert max(prune_at) < min(stop_at), (
        f"disk_cleanup.sh is invoked at line {max(prune_at)} but a `compose … down` runs at line "
        f"{min(stop_at)}. Pruning after the stack is down is what deleted the production monitor's "
        f"image. Move the disk cleanup above every stop.")
