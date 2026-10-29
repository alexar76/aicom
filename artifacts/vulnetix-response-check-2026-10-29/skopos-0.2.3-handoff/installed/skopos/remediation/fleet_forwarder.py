"""Carry orders and source out to the relay, and carry results back.

Runs beside the conductor, and is deliberately not part of it. It speaks the SAME agent protocol
a local deploy hand does — claim an order, report a result — so the conductor needs no knowledge
that some of its hands are on other machines, and no new trust: this process holds the agent
token because it already shares a host with the thing that issues it.

    conductor (loopback)  ──claim order──▶  forwarder  ──POST──▶  relay  ──▶  remote hand
                          ◀──post result──             ◀──GET───

Two things travel. The ORDER, unchanged and still signed by the conductor, so tampering by the
relay or by this process shows up as a signature failure on the hand. And the SOURCE, as a git
bundle of the one branch the order names — a bundle rather than a push because the relay has no
account and no shell, and a bundle can be verified by git itself before it is unpacked.

What this must never become: a decider. It does not choose services, does not sign, does not
inspect a patch and does not retry a deploy. If it dies, orders queue on the conductor and
nothing ships — which is the safe direction.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from typing import Any

import httpx

POLL_S = float(os.environ.get("SKOPOS_FORWARDER_POLL_S", "20") or 20)
_GIT_TIMEOUT_S = 300


def _hosts() -> list[str]:
    """Which hosts this forwarder carries for. Explicit: a forwarder that guessed would claim
    orders meant for a hand that is perfectly able to poll the conductor itself, and the order
    would be handed out ONCE — to the wrong courier."""
    raw = os.environ.get("SKOPOS_FORWARDER_HOSTS", "").strip()
    return [h.strip() for h in raw.split(",") if h.strip()]


class FleetForwarder:
    def __init__(self) -> None:
        self.conductor_url = os.environ.get("SKOPOS_CONDUCTOR_URL", "http://127.0.0.1:9402").rstrip("/")
        self.agent_token = os.environ.get("SKOPOS_AGENT_TOKEN", "").strip()
        self.relay_url = os.environ.get("SKOPOS_RELAY_URL", "").rstrip("/")
        self.relay_token = os.environ.get("SKOPOS_RELAY_TOKEN", "").strip()
        self.repo_url = os.environ.get("SKOPOS_FORWARDER_REPO_URL", "").strip()
        self.mirror = os.environ.get("SKOPOS_FORWARDER_MIRROR",
                                     "/var/lib/skopos-forwarder/aicom.git")
        self.hosts = _hosts()

    # ── plumbing ────────────────────────────────────────────────────────────────
    def _git(self, *args: str) -> tuple[int, str, str]:
        proc = subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=_GIT_TIMEOUT_S)
        return proc.returncode, proc.stdout, proc.stderr

    def _ensure_mirror(self) -> tuple[bool, str]:
        if os.path.isdir(os.path.join(self.mirror, "objects")):
            return True, "mirror present"
        if not self.repo_url:
            return False, "SKOPOS_FORWARDER_REPO_URL is unset — nothing to bundle from"
        os.makedirs(os.path.dirname(self.mirror), exist_ok=True)
        rc, _, err = self._git("clone", "--bare", self.repo_url, self.mirror)
        return (rc == 0), ("mirror cloned" if rc == 0 else f"clone failed: {err.strip()[:200]}")

    def send_source(self, branch: str) -> tuple[bool, str]:
        """Bundle one branch and hand it to the relay.

        Fetched fresh every time: the conductor pushed this branch seconds ago, and a mirror
        that is merely warm would bundle the previous attempt's commit — which the hand would
        then reject for not being the tip, reporting a confusing "wrong commit" instead of a
        stale courier.
        """
        ok, note = self._ensure_mirror()
        if not ok:
            return False, note
        rc, _, err = self._git("-C", self.mirror, "fetch", "--force", self.repo_url,
                               f"refs/heads/{branch}:refs/heads/{branch}")
        if rc != 0:
            return False, f"could not fetch '{branch}': {err.strip()[:200]}"
        rc, out, _ = self._git("-C", self.mirror, "rev-parse", f"refs/heads/{branch}")
        tip = out.strip() if rc == 0 else ""
        refs = self.relay_refs()
        if tip and refs.get(f"refs/heads/{branch}") == tip:
            # Already there — a retry, or a second order for the same commit. Bundling anyway
            # produces an EMPTY bundle, which git refuses outright, and the old fallback then
            # sent the entire history to fix nothing.
            return True, "already on the relay"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bundle")
        tmp.close()
        try:
            # Only what the relay is missing. A full-history bundle of this monorepo does not fit
            # through the ingress and would be carried again on every single remediation; with the
            # relay's own tips as the exclusion, a fix branch is two commits and a few kilobytes.
            excludes = [f"^{sha}" for sha in sorted(set(refs.values()))]
            rc, _, err = self._git("-C", self.mirror, "bundle", "create", tmp.name,
                                   f"refs/heads/{branch}", *excludes)
            if rc != 0 and excludes:
                # A tip the relay names but this mirror has never seen — a relay restored from a
                # backup, say — makes the exclusion unresolvable. Fall back to the whole branch
                # rather than failing the remediation. (The "nothing new" case is handled above,
                # so this fallback can no longer be reached by a duplicate commit.)
                rc, _, err = self._git("-C", self.mirror, "bundle", "create", tmp.name,
                                       f"refs/heads/{branch}")
            if rc != 0:
                return False, f"could not bundle '{branch}': {err.strip()[:200]}"
            with open(tmp.name, "rb") as fh:
                payload = fh.read()
            r = httpx.post(f"{self.relay_url}/fleet/v1/source", content=payload, timeout=300.0,
                           headers={"X-Relay-Token": self.relay_token, "X-Branch": branch,
                                    "content-type": "application/octet-stream"})
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            return bool(body.get("applied")), str(body.get("detail") or r.status_code)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def relay_refs(self) -> dict[str, str]:
        """What the relay already holds. Unreachable relay → empty, i.e. send everything, which
        is slow but correct; guessing it has something it does not produces a bundle git cannot
        apply."""
        try:
            r = httpx.get(f"{self.relay_url}/fleet/v1/refs",
                          headers={"X-Relay-Token": self.relay_token}, timeout=30.0)
            r.raise_for_status()
            refs = (r.json() or {}).get("refs") or {}
            return {k: v for k, v in refs.items() if isinstance(k, str) and isinstance(v, str)}
        except (httpx.HTTPError, ValueError):
            return {}

    # ── the loop ────────────────────────────────────────────────────────────────
    def carry_orders(self) -> list[dict[str, Any]]:
        carried = []
        for host in self.hosts:
            try:
                r = httpx.get(f"{self.conductor_url}/agent/v1/orders", params={"host": host},
                              headers={"X-Agent-Token": self.agent_token}, timeout=30.0)
                r.raise_for_status()
                body = r.json()
            except (httpx.HTTPError, ValueError) as exc:
                carried.append({"host": host, "carried": False,
                                "reason": f"conductor unreachable: {type(exc).__name__}"})
                continue
            order = (body or {}).get("order")
            if not order:
                continue
            # Source first. An order that arrives before the commit it names would be claimed by
            # the hand, fail to find the branch, and be spent — orders are handed out once.
            branch = str(order.get("branch") or order.get("ref") or "").strip()
            source_note = "no branch in order"
            if branch:
                ok, source_note = self.send_source(branch)
                if not ok:
                    self.report({"order_id": body.get("order_id"),
                                 "result": {"deployed": False, "refused": True,
                                            "reason": f"forwarder could not deliver the source: "
                                                      f"{source_note}", "host": host}})
                    carried.append({"host": host, "carried": False, "reason": source_note})
                    continue
            try:
                httpx.post(f"{self.relay_url}/fleet/v1/orders",
                           json={"host": host, "order_id": body.get("order_id"), "order": order},
                           headers={"X-Relay-Token": self.relay_token}, timeout=30.0)
            except httpx.HTTPError as exc:
                carried.append({"host": host, "carried": False,
                                "reason": f"relay unreachable: {type(exc).__name__}"})
                continue
            carried.append({"host": host, "carried": True, "order_id": body.get("order_id"),
                            "source": source_note})
        return carried

    def report(self, payload: dict[str, Any]) -> bool:
        try:
            httpx.post(f"{self.conductor_url}/agent/v1/result", json=payload,
                       headers={"X-Agent-Token": self.agent_token}, timeout=30.0)
            return True
        except httpx.HTTPError:
            return False

    def carry_results(self) -> int:
        try:
            r = httpx.get(f"{self.relay_url}/fleet/v1/results",
                          headers={"X-Relay-Token": self.relay_token}, timeout=30.0)
            r.raise_for_status()
            results = (r.json() or {}).get("results") or []
        except (httpx.HTTPError, ValueError):
            return 0
        delivered = 0
        for entry in results:
            if self.report({"order_id": entry.get("order_id"), "result": entry.get("result") or {}}):
                delivered += 1
        return delivered

    def tick(self) -> dict[str, Any]:
        return {"orders": self.carry_orders(), "results": self.carry_results()}

    def run_forever(self) -> None:  # pragma: no cover - long-running loop
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - a courier that dies stops the fleet healing
                pass
            time.sleep(POLL_S)


def main() -> None:  # pragma: no cover - process entrypoint
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("skopos.forwarder")
    fw = FleetForwarder()
    log.info("forwarder starting: conductor=%s relay=%s hosts=%s",
             fw.conductor_url, fw.relay_url or "(unset)", ", ".join(fw.hosts) or "(NONE)")
    if not fw.hosts:
        log.warning("no SKOPOS_FORWARDER_HOSTS — this courier will carry nothing")
    if not fw.relay_url or not fw.relay_token:
        log.warning("relay url/token unset — orders cannot leave this host")
    fw.run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
