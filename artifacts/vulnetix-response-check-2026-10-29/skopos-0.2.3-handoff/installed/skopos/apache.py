"""Apache access log parser — Apache combined / common compatible with nginx combined."""

from __future__ import annotations

from .nginx import parse_access_line

__all__ = ["parse_access_line"]
