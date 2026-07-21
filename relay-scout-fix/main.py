#!/usr/bin/env python3
"""Backend entrypoint for factory runtime E2E (binds :8000)."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("relay_scout.api:app", host="0.0.0.0", port=8000)
