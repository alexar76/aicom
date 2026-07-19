"""Shared helpers for logging suppressed exceptions (audit: avoid silent ``pass``)."""

from __future__ import annotations

import logging
from typing import Any


def log_suppressed(
    logger: logging.Logger,
    message: str,
    *args: Any,
    exc_info: bool | BaseException = True,
    level: int = logging.DEBUG,
) -> None:
    """Log a non-fatal exception instead of swallowing it silently."""
    logger.log(level, message, *args, exc_info=exc_info)
