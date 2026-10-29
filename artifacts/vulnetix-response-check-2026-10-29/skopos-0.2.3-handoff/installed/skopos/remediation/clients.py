"""Offline-safe clients the conductor uses to reach the other agents.

Every client degrades gracefully: if an endpoint is unconfigured or unreachable it returns a
typed "not done" result rather than raising, so a demo runs end-to-end with nothing live and a
production outage never crashes the conductor mid-job.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class MomusClient:
    """Talk to MOMUS over its A2A / HTTP surface: re-test a finding (the deploy gate)."""

    def __init__(self, base_url: str, timeout_s: float = 30.0, operator_token: str | None = None,
                 *, transport: Any = None):
        self.base_url = (base_url or "").strip().rstrip("/")
        self._timeout = timeout_s
        self._transport = transport      # test hook (httpx.ASGITransport)
        # MOMUS's /retest is a CONTROL route: it makes MOMUS act, so it is operator-token gated in
        # production. The conductor must present that token or every gate call comes back 403 and
        # the job loops to "inconclusive" until its retries are exhausted — which is exactly what a
        # live run showed after the gate was added and this caller was not updated with it.
        self._token = (operator_token if operator_token is not None
                       else os.environ.get("MOMUS_OPERATOR_TOKEN", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    async def retest(self, finding_id: str, *, candidate: bool = False) -> dict[str, Any]:
        """Return MOMUS's signed FixVerdict dict, or a fail-closed stub. Never raises.

        ``candidate=True`` asks for the PRE-promotion verdict — MOMUS probes the freshly built
        candidate container, so the answer is about the image that is about to ship rather than about
        the unpatched one still running. The signed verdict records which it examined (``gated``),
        and the node agent refuses to promote an image on a ``live`` verdict."""
        if not self.configured:
            return {"finding_id": finding_id, "fixed": False, "outcome": "inconclusive",
                    "detail": "no MOMUS url configured", "signature": {}}
        headers = {"x-momus-operator": self._token} if self._token else {}
        kwargs: dict[str, Any] = {"timeout": self._timeout, "headers": headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        try:
            async with httpx.AsyncClient(**kwargs) as c:
                r = await c.post(self.base_url + "/retest",
                                 json={"finding_id": finding_id, "candidate": candidate})
                r.raise_for_status()
                body = r.json()
            # MOMUS answers 200 with an `error` body for a finding or target it cannot resolve. That
            # is NOT a verdict about the code — it is a plumbing failure, and reading it as
            # "still vulnerable" is the same dishonesty as calling an unreachable target a pass. The
            # conductor must escalate naming the real cause instead of blaming the patch.
            if not isinstance(body, dict) or not isinstance(body.get("fixed"), bool):
                err = (body or {}).get("error") if isinstance(body, dict) else None
                return {"finding_id": finding_id, "fixed": False, "outcome": "inconclusive",
                        "detail": f"MOMUS could not run the gate: {err or 'malformed verdict'}"
                                  + (" — the finding is not in MOMUS's corpus (wrong instance, or "
                                     "it was never recorded)" if err == "unknown_finding" else ""),
                        "signature": {}}
            return body
        except httpx.HTTPStatusError as exc:
            # Distinguish "refused" from "unreachable": a 403/503 here means the conductor is not
            # authorised, which an operator must fix — not something to retry into exhaustion.
            code = exc.response.status_code
            hint = (" — the conductor is missing MOMUS_OPERATOR_TOKEN (the /retest gate is "
                    "operator-only in production)") if code in (401, 403, 503) else ""
            return {"finding_id": finding_id, "fixed": False, "outcome": "inconclusive",
                    "detail": f"MOMUS refused the re-test: HTTP {code}{hint}", "signature": {}}
        except (httpx.HTTPError, ValueError) as exc:
            return {"finding_id": finding_id, "fixed": False, "outcome": "inconclusive",
                    "detail": f"MOMUS unreachable: {type(exc).__name__}", "signature": {}}


class FactoryClient:
    """Ask the AI-Factory to produce a patch for the at-fault component. In dry-run (default) it
    returns a synthetic 'patch produced' so the loop is testable without a live Factory."""

    # The route asks the model for full file contents and a mid-tier model takes minutes on a few
    # hundred lines. This must EXCEED the service's own LLM budget, or the client gives up first
    # and the conductor never sees the reason.
    #
    # Configurable because 300 was measured to be too tight in practice: the live model answers
    # this prompt in 79-119s, which leaves the 240s budget marginal, and marginal means it fails
    # during an incident — which is exactly when it ran. Raising the budget then needs headroom
    # above it, so the two move together.
    def __init__(self, base_url: str, *, dry_run: bool = True, timeout_s: float | None = None,
                 api_key: str | None = None):
        if timeout_s is None:
            try:
                timeout_s = float(os.environ.get("SKOPOS_FACTORY_TIMEOUT_S", "") or 300.0)
            except ValueError:
                timeout_s = 300.0
        self.base_url = (base_url or "").strip().rstrip("/")
        self.dry_run = bool(dry_run)
        # The fix route is shared-secret gated and fail-closed in production. Without this header
        # every call comes back 401 and the job escalates blaming a patch that was never requested —
        # the same shape as the MomusClient operator-token omission a live run already found once.
        self._api_key = (api_key if api_key is not None
                         else os.environ.get("AIFACTORY_REMEDIATION_KEY", "")).strip()
        # An unconfigured Factory used to fall back to dry-run SYNTHESIS even when the conductor was
        # live (`dry_run or not base_url`). That combination is the worst of both: the loop hands out
        # a made-up patch, signs a real DeployOrder for it, and a node agent recreates the container
        # from the SAME image — a redeploy that fixes nothing, presented as a fix. Outside dry-run a
        # missing URL is a configuration fault and says so.
        self.unconfigured = not self.base_url and not self.dry_run
        self._timeout = timeout_s

    async def request_fix(self, ticket: dict[str, Any],
                          previous_failure: str = "", attempt: int = 1) -> dict[str, Any]:
        if self.unconfigured:
            return {"ok": False, "config_error": True,
                    "error": "SKOPOS_FACTORY_URL is unset while the conductor is live — refusing to "
                             "synthesize a patch. Set the Factory URL, or run in dry-run."}
        if self.dry_run:
            return {"ok": True, "dry_run": True,
                    "patch": {"component": ticket.get("component"), "summary": "dry-run: patch synthesized",
                              "image": f"{ticket.get('component')}:patched-{ticket.get('finding_id','')[:8]}"}}
        # NOTE: no Factory build serves /api/remediation/fix yet. Autonomous patch authoring is
        # designed but deliberately not enabled — see momus/docs/fix-provenance.md ("the fix step
        # stays a fixture flip"). Outside dry-run this call therefore 404s today, and it must say
        # so: reporting a 404 as "Factory unreachable" sent operators hunting a network fault.
        path = "/api/remediation/fix"
        try:
            headers = {"x-remediation-key": self._api_key} if self._api_key else {}
            async with httpx.AsyncClient(timeout=self._timeout, headers=headers) as c:
                body: dict[str, Any] = {"ticket": ticket, "attempt": int(attempt)}
                if previous_failure:
                    # The retry is only worth making if it knows why the last one was refused.
                    body["previous_failure"] = previous_failure
                r = await c.post(self.base_url + path, json=body)
                r.raise_for_status()
                return {"ok": True, **r.json()}
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            hint = (" — autonomous fix authoring is not enabled on this Factory build; "
                    "run the conductor in dry-run, or implement the route") if code == 404 else ""
            if code in (401, 403):
                hint = (" — the conductor is missing AIFACTORY_REMEDIATION_KEY (the fix route is "
                        "shared-secret gated)")
            elif code == 503:
                hint = (" — the Factory refuses to author patches for an unauthenticated caller "
                        "in production; set AIFACTORY_REMEDIATION_KEY on both sides")
            # A refused or unavailable route is a CONFIGURATION fault, not a patch that failed.
            # Retrying it three times and then blaming the fix is the same mistake the gate and the
            # unset-URL paths above already fixed.
            return {"ok": False, "http_status": code,
                    "config_error": code in (401, 403, 404, 503),
                    "error": f"Factory returned {code} for {path}{hint}"}
        except (httpx.HTTPError, ValueError) as exc:
            return {"ok": False, "error": f"Factory unreachable: {type(exc).__name__}"}
