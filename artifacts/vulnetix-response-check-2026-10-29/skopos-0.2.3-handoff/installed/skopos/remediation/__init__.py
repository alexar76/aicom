"""SKOPOS remediation — the conductor of the autonomous find → fix → verify → deploy loop.

MOMUS finds a hole and signs it, but MOMUS holds no fix and no deploy key. SKOPOS is the watcher
(σκοπός) that conducts the repair, reusing pieces that already exist:

    MOMUS ──(A2A: remediate task, signed ticket)──▶ SKOPOS conductor
                                                        │  drives the AI-Factory to write a patch
                                                        ▼
                                                    AI-Factory ──(patch / new image)──▶
                                                        │  asks MOMUS to re-test the patched build
                                                        ▼
    MOMUS ──(A2A: retest → signed "fixed" verdict)──▶ SKOPOS conductor
                                                        │  signs a DeployOrder embedding that verdict
                                                        ▼
                              SKOPOS node agent (already installed on the target host)
                                 · verifies BOTH signatures + a local service allowlist
                                 · redeploys ONLY that one allowlisted service
                                 · reports back → conductor triggers a final in-place MOMUS retest

Why the installed agents are the deployers: they already have a constrained, enrolled foothold on
each host (ticket-based enrollment, privdump/agent privilege split), so the conductor needs no SSH
and no fleet-wide key. The trust chain (MOMUS-signed fixed → SKOPOS-signed order → agent allowlist)
means a compromised conductor cannot ship arbitrary code, and a compromised agent can only redeploy
its own allowlisted services. Three roles, three keys, bounded blast radius.

Everything here is offline-/dry-run-safe by default: no Factory call, no real ``docker`` command,
and no deploy happens unless the operator explicitly wires the endpoints and flips the dry-run off.
"""

from skopos.remediation.deploy_order import DeployOrder, verify_deploy_chain
from skopos.remediation.jobs import Job, JobState, JobStore
from skopos.remediation.conductor import Conductor, RemediationConfig

__all__ = [
    "DeployOrder",
    "verify_deploy_chain",
    "Job",
    "JobState",
    "JobStore",
    "Conductor",
    "RemediationConfig",
]
