"""Reproduce the remaining shared-login refusal in SKOPOS 0.2.2.

Run from the workspace with:
    skopos/.venv/bin/python artifacts/vulnetix-review-2026-10-28/skopos_login_probe.py

This uses a temporary SQLite database, a controlled clock and mocked Streamlit
display/stop calls. It does not start a server, change credentials or issue
network requests. Calling register_failed_login directly after admission shows
what another already-admitted concurrent or pacing-exempt failure would do;
ordinary unknown-IP requests are themselves refused during the shared pause.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / "skopos"))

from skopos import app_auth, auth_store  # noqa: E402


class StopBeforePassword(Exception):
    """Stand-in for Streamlit's control-flow exception."""


def stop() -> None:
    raise StopBeforePassword()


def main() -> None:
    result = {
        "record": "GCVE-110-VULN-PYPI-2026-000644",
        "package": "skopos-fleet",
        "source_version": "0.2.2",
        "assessment": "partial fix: shared timed refusal remains for a new operator IP",
        "scope": "local source; no production or published wheel claim",
        "limitations": [
            "Failures are recorded through auth_store directly rather than a live browser.",
            "An ordinary unknown-IP attacker is also stopped during the shared pause.",
            "Refreshing the pause during its lifetime requires an already-admitted concurrent or exempt source.",
        ],
    }
    with TemporaryDirectory(prefix="skopos-review-") as tmp:
        db = str(Path(tmp) / "auth.sqlite")
        clock = [1000000.0]
        with patch.object(auth_store.time, "time", lambda: clock[0]), patch.dict(
            "os.environ",
            {
                "SKOPOS_LOGIN_GLOBAL_MAX_ATTEMPTS": "30",
                "SKOPOS_LOGIN_MAX_ATTEMPTS": "5",
                "SKOPOS_LOGIN_LOCKOUT_SECONDS": "300",
                "SKOPOS_LOGIN_KNOWN_DAYS": "30",
            },
        ):
            auth_store.clear_login_lockout("192.0.2.1", db_target=db)
            for n in range(37):
                auth_store.register_failed_login(f"198.51.100.{n}", db_target=db)
            result["after_37_distinct_failed_addresses"] = {
                "new_operator_own_lockout_seconds": auth_store.login_lockout_remaining_seconds(
                    "192.0.2.200", db_target=db
                ),
                "new_operator_shared_pause_seconds": auth_store.login_pace_seconds(
                    "192.0.2.200", db_target=db
                ),
                "known_operator_shared_pause_seconds": auth_store.login_pace_seconds(
                    "192.0.2.1", db_target=db
                ),
            }
            with patch.object(app_auth, "_client_ip", lambda: "192.0.2.200"), patch.object(
                app_auth,
                "login_lockout_remaining_seconds",
                lambda ip: auth_store.login_lockout_remaining_seconds(ip, db_target=db),
            ), patch.object(
                app_auth,
                "login_pace_seconds",
                lambda ip: auth_store.login_pace_seconds(ip, db_target=db),
            ), patch.object(app_auth.st, "info", lambda *args, **kwargs: None), patch.object(
                app_auth.st, "stop", stop
            ):
                try:
                    app_auth._check_login_lockout("en")
                except StopBeforePassword:
                    result["new_operator_gate"] = "st.stop before password form or verification"
                else:
                    result["new_operator_gate"] = "allowed"
            clock[0] += 59
            result["after_59_seconds_pause_remaining"] = auth_store.login_pace_seconds(
                "192.0.2.200", db_target=db
            )
            auth_store.register_failed_login("198.51.100.90", db_target=db)
            result["after_additional_admitted_failure_pause_remaining"] = auth_store.login_pace_seconds(
                "192.0.2.200", db_target=db
            )
            clock[0] += 60
            result["after_quiet_60_seconds_pause_remaining"] = auth_store.login_pace_seconds(
                "192.0.2.200", db_target=db
            )

    assert result["after_37_distinct_failed_addresses"] == {
        "new_operator_own_lockout_seconds": 0,
        "new_operator_shared_pause_seconds": 60,
        "known_operator_shared_pause_seconds": 0,
    }
    assert result["new_operator_gate"] == "st.stop before password form or verification"
    assert result["after_59_seconds_pause_remaining"] == 1
    assert result["after_additional_admitted_failure_pause_remaining"] == 60
    assert result["after_quiet_60_seconds_pause_remaining"] == 0
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
