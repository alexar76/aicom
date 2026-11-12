"""Emberline keys its pay limiter on request.client.host. Behind its own nginx container every buyer
has the same peer address, so eight invoices from eight different people close checkout for 15 min."""
from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["HUB_MODE"] = "fixture"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_DEMO"] = "true"
os.environ["JWT_SECRET"] = "test-secret-must-be-at-least-32b"
os.environ["PAY_MINT_SECRET"] = "test-mint"
os.environ["PAY_MODE"] = "fixture"
os.environ["DESK_MODE"] = "live"
os.environ["PAY_BASE_RPC_URL"] = "http://127.0.0.1:9"
os.environ["PAY_BASE_ADDRESS"] = "0x1111111111111111111111111111111111111111"

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import Base, engine
from app.main import create_app
from app.security import reset_rate_limits


def test_eight_buyers_close_checkout_for_everyone():
    get_settings.cache_clear(); reset_rate_limits()
    Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    with TestClient(create_app()) as client:   # every request has the same peer, like nginx -> api
        codes = []
        for i in range(9):
            res = client.post("/api/public/pay/invoices", json={"plan": "solo"},
                              headers={"X-Forwarded-For": f"203.0.113.{i + 1}"})
            codes.append(res.status_code)
        print(codes)
        assert codes[:8] == [200] * 8 and codes[8] == 429
