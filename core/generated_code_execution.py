"""Fail closed before generated code crosses the factory's host boundary.

A subprocess, venv, working directory and scrubbed environment do not restrict
filesystem, process or socket access. Container/VM execution must be supplied by
the caller; this module never treats those measures as a security sandbox.
"""

from __future__ import annotations

import os

LOCAL_HOST_OPT_IN = "AIFACTORY_UNSAFE_ALLOW_HOST_GENERATED_CODE"
ISOLATION_REASON = "generated_code_isolation_required"


class GeneratedCodeIsolationRequired(OSError):
    """Generated code cannot execute with factory host privileges."""


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def unsafe_host_execution_requested() -> bool:
    return _truthy(LOCAL_HOST_OPT_IN)


def require_host_execution_opt_in() -> None:
    """Allow an explicit disposable local run, never production or a public demo.

    Default refusal also protects public instances that forgot their production
    marker. An operator opting into local host execution must not expose customer
    product creation; the public creation route enforces that independently.
    """
    production_tag = os.environ.get("AIFACTORY_ENV", "").strip().lower() in {"production", "prod", "live"}
    if (not unsafe_host_execution_requested() or production_tag
            or any(_truthy(name) for name in (
                "AIFACTORY_PROD", "AIFACTORY_PRODUCTION", "AIFACTORY_DEMO_READONLY",
                "AIFACTORY_SANDBOX_REQUIRE_CONTAINER",
            ))):
        raise GeneratedCodeIsolationRequired(
            f"{ISOLATION_REASON}: generated tests, build hooks and applications require "
            "an isolated worker/container. Host execution is refused. "
            f"{LOCAL_HOST_OPT_IN}=1 is only for disposable, private local development."
        )
