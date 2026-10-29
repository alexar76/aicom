"""LOGOS entry point — ``python -m logos.main`` or ``uvicorn logos.main:app``."""

from __future__ import annotations

import os

import uvicorn

from logos.app import create_app
from logos.config import LogosConfig

app = create_app()


def main() -> None:
    cfg = LogosConfig.from_env()
    uvicorn.run(
        "logos.main:app",
        host="0.0.0.0",
        port=cfg.port,
        reload=not cfg.prod,
        log_level="info" if cfg.prod else "debug",
    )


if __name__ == "__main__":
    main()
