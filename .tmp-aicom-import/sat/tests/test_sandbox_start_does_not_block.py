"""An admin sandbox start must not hold the HTTP request open for the bootstrap.

The bootstrap creates a venv, installs dependencies and builds the SPA — the start
response's own ``startup_warning`` calls that "several minutes". While it ran inside the
request, any interruption on the client side (a VPN reconnect, an idle proxy, a closed
laptop) aborted the POST *after* the server had already created the sandbox: nginx logged a
499, the browser reported a bare "NetworkError when attempting to fetch resource.", and the
operator was shown a dead end while a working sandbox finished booting behind it.

The client was always written for the non-blocking contract — it polls ``GET /ready/{id}``
and drives a progress bar off ``startup_phase`` — but only the storefront route honoured it.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from web.backend.api import sandbox as sandbox_api


SLOW_BOOTSTRAP_SECONDS = 3.0


@pytest.fixture
def slow_bootstrap(tmp_path, monkeypatch):
    """A product whose bootstrap takes measurably longer than a start call should."""
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    (code_dir / "index.html").write_text("<html><body>x</body></html>")

    started = threading.Event()
    finished = threading.Event()

    def _bootstrap(sandbox_id, product_id, product_code_dir, port, *, storefront=False):
        started.set()
        time.sleep(SLOW_BOOTSTRAP_SECONDS)
        finished.set()
        return (
            {"enabled": True, "proxy_prefix": f"/api/sandbox/backend/{sandbox_id}", "status": "ok"},
            {"enabled": False, "proxy_prefix": None, "status": "skipped"},
        )

    monkeypatch.setattr(sandbox_api, "_get_product_code_dir", lambda pid: code_dir)
    monkeypatch.setattr(sandbox_api, "_run_full_sandbox_bootstrap", _bootstrap)
    monkeypatch.setattr(sandbox_api, "_ensure_sandbox_capacity", lambda **kw: None)
    monkeypatch.setattr(sandbox_api, "_save_registry", lambda: None)
    monkeypatch.setattr(
        sandbox_api, "materialize_spec_landing_on_disk", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(sandbox_api, "ensure_storefront_preview_index", lambda *a, **k: None)
    return started, finished


@pytest.mark.parametrize("storefront", [False, True])
def test_start_returns_before_the_bootstrap_finishes(slow_bootstrap, storefront):
    started, finished = slow_bootstrap
    t0 = time.monotonic()
    result = sandbox_api._start_sandbox_for_product(
        "prod-slow-stack", storefront=storefront
    )
    elapsed = time.monotonic() - t0

    assert result["sandbox_id"].startswith("sandbox-")
    assert elapsed < SLOW_BOOTSTRAP_SECONDS / 2, (
        f"start blocked for {elapsed:.2f}s of a {SLOW_BOOTSTRAP_SECONDS}s bootstrap — an "
        "interrupted client loses the response and sees a bare NetworkError"
    )
    # The work still happens; it is just not on the request thread.
    assert started.wait(timeout=SLOW_BOOTSTRAP_SECONDS), "bootstrap never started"
    assert finished.wait(timeout=SLOW_BOOTSTRAP_SECONDS * 3), "bootstrap never completed"


def test_readiness_is_how_the_client_learns_the_stack_is_up(slow_bootstrap):
    """The non-blocking response must still name the sandbox to poll."""
    _started, finished = slow_bootstrap
    result = sandbox_api._start_sandbox_for_product("prod-slow-stack", storefront=False)
    sid = result["sandbox_id"]
    assert result.get("startup_phase") in {"starting", "bootstrapping"}
    assert sid in sandbox_api._active_sandboxes
    assert finished.wait(timeout=SLOW_BOOTSTRAP_SECONDS * 3)


def test_publisher_opts_into_waiting(slow_bootstrap):
    """`working_app_publish` decides publishability from preview_api/compose_preview, which
    are only populated once the stack is actually up — so it, and only it, waits."""
    _started, _finished = slow_bootstrap
    t0 = time.monotonic()
    result = sandbox_api._start_sandbox_for_product(
        "prod-slow-stack", storefront=False, wait_for_bootstrap=True
    )
    elapsed = time.monotonic() - t0

    assert elapsed >= SLOW_BOOTSTRAP_SECONDS, "wait_for_bootstrap returned early"
    assert result["preview_api"]["enabled"] is True
    assert result["preview_api"]["status"] == "ok"


def test_working_app_publish_asks_to_wait():
    """Guard the call site itself: without the flag the publisher reads empty payloads and
    reports `working_app_not_live` for every full_software product."""
    from web.backend.services import working_app_publish

    seen: dict[str, object] = {}

    def _fake_start(product_id, *, storefront=False, wait_for_bootstrap=False):
        seen["storefront"] = storefront
        seen["wait_for_bootstrap"] = wait_for_bootstrap
        return {}

    with patch.object(working_app_publish, "_sandbox_starter", lambda: _fake_start):
        working_app_publish.try_publish_working_app("prod-anything")

    assert seen == {"storefront": False, "wait_for_bootstrap": True}
