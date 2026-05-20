"""
JWT encode/decode via PyJWT (replaces unmaintained python-jose).

Used for admin and customer bearer tokens (HS256).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional, Union

import jwt
from jwt.exceptions import PyJWTError

JwtPayload = dict[str, Any]
TimeClaim = Union[int, float, datetime]


def encode_hs256(payload: Mapping[str, Any], secret: str, *, algorithm: str = "HS256") -> str:
    token = jwt.encode(dict(payload), secret, algorithm=algorithm)
    return token if isinstance(token, str) else token.decode("utf-8")


def decode_hs256(token: str, secret: str, *, algorithms: Optional[list[str]] = None) -> JwtPayload:
    alg = algorithms or ["HS256"]
    return jwt.decode(token, secret, algorithms=alg)


def decode_hs256_optional(
    token: str,
    secret: str,
    *,
    algorithms: Optional[list[str]] = None,
) -> Optional[JwtPayload]:
    try:
        return decode_hs256(token, secret, algorithms=algorithms)
    except PyJWTError:
        return None
