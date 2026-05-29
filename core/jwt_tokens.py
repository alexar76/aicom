"""
JWT encode/decode via PyJWT (replaces unmaintained python-jose).

Used for admin and customer bearer tokens (HS256).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import jwt
from jwt.exceptions import PyJWTError

if TYPE_CHECKING:
    from collections.abc import Mapping

JwtPayload = dict[str, Any]
TimeClaim = int | float | datetime


def encode_hs256(payload: Mapping[str, Any], secret: str, *, algorithm: str = "HS256") -> str:
    token = jwt.encode(dict(payload), secret, algorithm=algorithm)
    return token if isinstance(token, str) else token.decode("utf-8")


def decode_hs256(token: str, secret: str, *, algorithms: list[str] | None = None) -> JwtPayload:
    alg = algorithms or ["HS256"]
    return jwt.decode(token, secret, algorithms=alg)


def decode_hs256_optional(
    token: str,
    secret: str,
    *,
    algorithms: list[str] | None = None,
) -> JwtPayload | None:
    try:
        return decode_hs256(token, secret, algorithms=algorithms)
    except PyJWTError:
        return None
