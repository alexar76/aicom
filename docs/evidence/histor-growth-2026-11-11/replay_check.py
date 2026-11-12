"""Replay two archived AI Applyd tool lists through the local HISTOR HTTP app."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "histor"))

import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from histor.app import create_app  # noqa: E402
from histor.check import CHECK_TYPE  # noqa: E402
from histor.config import load_settings  # noqa: E402
from histor.logbook import verify_document  # noqa: E402
from histor.mcpclient import Observation  # noqa: E402
from histor.registry import Target  # noqa: E402
from histor.service import build  # noqa: E402
from histor.subject import REGISTRY_OFFICIAL  # noqa: E402
from tests.conftest import Clock, FakeScanner  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", type=int, metavar="LOCAL_PORT", help="Serve the local browser fixture instead")
    args = parser.parse_args()
    case = json.loads((ROOT / "artifacts/histor-legion-case-2026-11-03/histor.json").read_text())
    transitions = json.loads((ROOT / "artifacts/histor-legion-case-2026-11-03/histor-transitions.json").read_text())
    sample = case["transition"]["from"]
    later = case["snapshot"]["toolSetDigest"]
    server = case["snapshot"]
    target = Target(id=server["id"], name=server["name"], endpoint=server["endpoint"], transport="streamable-http",
                    registry=REGISTRY_OFFICIAL, title="AI Applyd", description="Archived observation for local QA.",
                    version="1.0.0", repository=None, website=None, skip_reason=None)

    class ArchiveReader:
        tools = case["toolsets"][sample]

        def list_tools(self, endpoint: str) -> Observation:
            assert endpoint == target.endpoint
            return Observation(status="ok", tools=self.tools, protocol_version="2025-06-18", pages=1)

    reader = ArchiveReader()
    clock = Clock("2026-10-19T21:37:07Z")
    scanner = FakeScanner()
    with TemporaryDirectory(prefix="histor-growth-replay-") as data, patch.dict(os.environ, {
        "HISTOR_DATA_DIR": data, "HISTOR_CRAWL_INTERVAL_S": "0", "HISTOR_REMOTE_INTERVAL_S": "0",
        "HISTOR_CRAWL_ON_START": "0", "HISTOR_PUBLIC_BASE": f"http://127.0.0.1:{args.serve or 9490}",
        "HISTOR_LANDING_DIR": str(ROOT / "histor/docs/landing"), "HISTOR_WATCH_DEMO": "1",
    }, clear=True):
        svc = build(load_settings(), crawler_kwargs={"reader": reader, "clock": clock,
                                                     "harvest_fn": lambda _url: [target]})
        try:
            svc.crawler.scanner = svc.checker.scanner = scanner
            svc.crawler.run()
            clock.now = datetime.fromisoformat(next(row["observedAt"] for row in transitions if row["toToolSetDigest"] == later))
            reader.tools = case["toolsets"][later]
            svc.crawler.run()
            app = create_app(svc)
            if args.serve:
                uvicorn.run(app, host="127.0.0.1", port=args.serve)
                return
            with TestClient(app) as client:
                answer = client.post("/api/v1/check", json={"endpoint": target.endpoint, "toolSetDigest": sample})
                answer.raise_for_status()
                result = answer.json()
                assert result["target"]["id"] == target.id and result["match"] == "previously-observed"
                assert result["observed"]["toolSetDigest"] == later
                assert verify_document(result, svc.key.did, CHECK_TYPE)
                feed = client.get("/feed.xml", params={"watch": target.id})
                assert feed.status_code == 200 and f"/s/{target.id}" in feed.text
                journey = client.post("/api/v1/journey/qa/sample_succeeded", headers={
                    "Origin": svc.settings.public_base, "Sec-Fetch-Site": "same-origin",
                })
                assert journey.status_code == 204
                print(json.dumps({"target": target.id, "recordedDigest": sample, "laterDigest": later,
                                  "match": result["match"], "localSignatureVerified": True,
                                  "atomRecordLink": True, "qaEventStatus": journey.status_code}, indent=2))
        finally:
            svc.close()


if __name__ == "__main__":
    main()
