from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from relay_scout.alerts import send_alert
from relay_scout.config import load_config
from relay_scout.diff_engine import compute_diff
from relay_scout.models import EndpointTarget
from relay_scout.poller import poll_endpoint
from relay_scout.storage import get_last_two_snapshots, save_snapshot

app = typer.Typer(help="Relay Scout — ecosystem health watchdog")
console = Console()


async def _check_one(client: httpx.AsyncClient, target: EndpointTarget) -> None:
    previous = get_last_two_snapshots(target.name)
    prev = previous[-1] if previous else None
    snap = await poll_endpoint(client, target)
    save_snapshot(snap)

    if snap.error or snap.status_code >= 400 or snap.status_code < 200:
        status = "DOWN"
        await send_alert(
            target,
            snap,
            "downtime",
            snap.error or f"HTTP {snap.status_code}",
        )
    else:
        status = "UP"
        diff = compute_diff(prev, snap)
        if diff.has_changes:
            await send_alert(
                target,
                snap,
                "drift",
                f"Drift detected: {diff.summary}",
            )

    console.print(f"{target.name}: {status} ({snap.status_code}, {snap.latency_ms:.0f}ms)")


async def _run_check(config: Path) -> None:
    targets = load_config(config)
    table = Table(title="Relay Scout check")
    table.add_column("Target")
    table.add_column("URL")
    table.add_column("Status")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for target in targets:
            previous = get_last_two_snapshots(target.name)
            prev = previous[-1] if previous else None
            snap = await poll_endpoint(client, target)
            save_snapshot(snap)
            if snap.error or snap.status_code >= 400 or snap.status_code < 200:
                st = f"DOWN ({snap.error or snap.status_code})"
                await send_alert(target, snap, "downtime", st)
            else:
                st = f"UP {snap.status_code}"
                diff = compute_diff(prev, snap)
                if diff.has_changes:
                    st += f" drift {diff.summary}"
                    await send_alert(target, snap, "drift", diff.summary)
            table.add_row(target.name, target.url, st)
    console.print(table)


@app.command("check")
def check_cmd(
    config: Path = typer.Option(Path("relay-scout.yaml"), "--config", "-c", help="YAML config path"),
) -> None:
    """One-shot health pass across configured targets."""
    asyncio.run(_run_check(config))


@app.command("diff")
def diff_cmd(
    name: str = typer.Argument(..., help="Endpoint name"),
    config: Path = typer.Option(Path("relay-scout.yaml"), "--config", "-c"),
) -> None:
    """Compare the last two snapshots for a target."""
    _ = load_config(config)
    snaps = get_last_two_snapshots(name)
    if len(snaps) < 2:
        console.print(f"[yellow]Need at least two snapshots for {name}[/yellow]")
        raise typer.Exit(code=1)
    diff = compute_diff(snaps[0], snaps[1])
    console.print(f"Diff for [bold]{name}[/bold]: {diff.summary}")
    if diff.added_fields:
        console.print("Added:", ", ".join(diff.added_fields))
    if diff.removed_fields:
        console.print("Removed:", ", ".join(diff.removed_fields))
    if diff.changed_fields:
        console.print("Changed:", ", ".join(diff.changed_fields))


@app.command("watch")
def watch_cmd(
    config: Path = typer.Option(Path("relay-scout.yaml"), "--config", "-c"),
    once: bool = typer.Option(False, "--once", help="Run a single pass then exit"),
    interval: int = typer.Option(60, "--interval", help="Seconds between passes"),
) -> None:
    """Scheduled polling loop."""

    async def _loop() -> None:
        while True:
            await _run_check(config)
            if once:
                break
            await asyncio.sleep(max(5, interval))

    asyncio.run(_loop())


if __name__ == "__main__":
    app()
