#!/usr/bin/env python3
"""Run Relay Scout ops API on port 8000."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("relay_scout.api:app", host="0.0.0.0", port=8000)
