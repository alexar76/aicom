"""Callables invoked by ``run_e2e_in_subprocess`` in unit tests."""

from __future__ import annotations

import os
import time


def ok(product_id: str, data_root: str | None = None) -> dict:
    return {"passed": True, "skipped": False, "product_id": product_id, "data_root": data_root}


def boom(product_id: str, data_root: str | None = None) -> dict:
    os.kill(os.getpid(), 9)
    return {"passed": True, "product_id": product_id}


def sleepy(product_id: str, data_root: str | None = None) -> dict:
    time.sleep(30)
    return {"passed": True, "product_id": product_id}
