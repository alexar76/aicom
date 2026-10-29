"""Read-only probe of SKOPOS IP extraction with the actual Streamlit 1.66.1 client.

Run from aicom using the existing SKOPOS venv, with a public Streamlit wheel:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=skopos skopos/.venv/bin/python \
  artifacts/vulnetix-response-check-2026-10-29/skopos_streamlit_peer_probe.py \
  /tmp/aicom-streamlit-1.66.1.whl

No network server is started. Runtime/session-manager lookups point at a real
StarletteSessionClient, whose input is a synthetic Starlette WebSocket scope.
Application sources are imported unchanged. IP addresses are synthetic fixtures.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])

import streamlit
import streamlit.runtime as runtime
import streamlit.runtime.scriptrunner as scriptrunner
from starlette.websockets import WebSocket
from streamlit.runtime.context import StreamlitHeaders
from streamlit.web.server.starlette.starlette_websocket import StarletteSessionClient

from skopos import app_auth, auth_store


async def main():
    async def receive():
        return {"type": "websocket.disconnect"}

    async def send(message):
        pass

    rows = []
    for spoof in ["198.51.100.1", "198.51.100.2"]:
        websocket = WebSocket(
            {"type": "websocket", "client": ("93.184.216.34", 12345),
             "headers": [(b"x-real-ip", spoof.encode())]},
            receive, send,
        )
        client = StarletteSessionClient(websocket)
        manager = SimpleNamespace(get_session_info=lambda sid: SimpleNamespace(client=client))
        fake_st = SimpleNamespace(context=SimpleNamespace(
            headers=StreamlitHeaders(client.client_context.headers)))
        with patch.object(runtime, "exists", return_value=True), \
             patch.object(runtime, "get_instance", return_value=SimpleNamespace(_session_mgr=manager)), \
             patch.object(scriptrunner, "get_script_run_ctx", return_value=SimpleNamespace(session_id="test")), \
             patch.object(app_auth, "st", fake_st):
            rows.append({
                "streamlit": streamlit.__version__,
                "actual_peer": client.client_context.remote_ip,
                "request_attribute_exists": hasattr(client, "request"),
                "extracted_peer": app_auth._websocket_peer(),
                "supplied_header": spoof,
                "login_lockout_key": app_auth._client_ip(),
            })
        await client.aclose()

    # Demonstrate the downstream budget distinction using the unchanged auth store.
    with tempfile.TemporaryDirectory(prefix="aicom-skopos-ip-probe-") as tmpdir:
        db = str(Path(tmpdir) / "auth.sqlite")
        known_ip = "198.51.100.1"
        unknown_ip = "198.51.100.2"
        auth_store.clear_login_lockout(known_ip, db_target=db)
        for n in range(45):
            auth_store.register_failed_login(f"192.0.2.{n+1}", db_target=db)
        budget = {
            "known_ip": known_ip,
            "unknown_ip": unknown_ip,
            "known_ip_pace_seconds": auth_store.login_pace_seconds(known_ip, db_target=db),
            "unknown_ip_pace_seconds": auth_store.login_pace_seconds(unknown_ip, db_target=db),
        }
        for _ in range(5):
            auth_store.register_failed_login(unknown_ip, db_target=db)
        budget["exhausted_spoofed_ip_lockout_seconds"] = auth_store.login_lockout_remaining_seconds(
            unknown_ip, db_target=db)
        budget["fresh_spoofed_ip_lockout_seconds"] = auth_store.login_lockout_remaining_seconds(
            "198.51.100.3", db_target=db)
    print(json.dumps({"peer_probe": rows, "budget_probe": budget}, indent=2))


asyncio.run(main())
