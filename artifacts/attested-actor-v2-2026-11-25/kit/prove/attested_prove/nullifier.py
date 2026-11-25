"""Linkable ring signatures over Ed25519 — the nullifier claim primitive.

A holder proves *"I am one of the keys registered for this scope"* and can do it
**once**: the signature carries a key image that is deterministic for the signer
and unlinkable to any particular ring member. Registering a claim reveals a
public key; spending it reveals only the scope and the image.

**What this is and is not.** It is an LSAG (linkable spontaneous anonymous group
signature) — a real zero-knowledge proof of membership with a real double-spend
nullifier, roughly the Monero construction on the Ed25519 group. It is **not** a
SNARK: the anonymity set is exactly the ring the verifier is given, so privacy is
bounded by how many keys share the scope. A one-member ring hides nothing, and
the API says so rather than pretending otherwise.

The one trap worth naming, because getting it wrong silently destroys the whole
property: ``hash_to_point`` must produce a point of **unknown discrete log**. The
obvious shortcut — hash to a scalar and multiply the base point — makes
``H(P) = kG`` with ``k`` known, so the key image ``I = x·H(P) = k·P`` becomes
computable by anyone holding the ring. Every member's image could be derived and
the signer identified. Try-and-increment decompression is used instead.
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Sequence

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I_SQRT = pow(2, (P - 1) // 4, P)
DOMAIN = b"attested-prove/nullifier/v1"

Point = tuple[int, int, int, int]  # extended: X, Y, Z, T


def _inv(value: int) -> int:
    return pow(value, P - 2, P)


def point_add(a: Point, b: Point) -> Point:
    a1 = (a[1] - a[0]) * (b[1] - b[0]) % P
    a2 = (a[1] + a[0]) * (b[1] + b[0]) % P
    a3 = 2 * a[3] * b[3] * D % P
    a4 = 2 * a[2] * b[2] % P
    e, f, g, h = a2 - a1, a4 - a3, a4 + a3, a2 + a1
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def point_double(a: Point) -> Point:
    return point_add(a, a)


IDENTITY: Point = (0, 1, 1, 0)


def scalar_mul(point: Point, scalar: int) -> Point:
    # Do not reduce here: subgroup validation needs the actual product [L]P.
    # Reducing L to zero makes every curve point appear to have prime order.
    if scalar < 0:
        raise ValueError("scalar must be non-negative")
    result = IDENTITY
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = point_add(result, addend)
        addend = point_double(addend)
        scalar >>= 1
    return result


def _recover_x(y: int, sign: int) -> int | None:
    if y >= P:
        return None
    xx = (y * y - 1) * _inv(D * y * y + 1) % P
    if xx == 0:
        return None if sign else 0
    x = pow(xx, (P + 3) // 8, P)
    if x * x % P != xx:
        x = x * I_SQRT % P
    if x * x % P != xx:
        return None
    if x & 1 != sign:
        x = P - x
    return x


def decompress(data: bytes) -> Point | None:
    if len(data) != 32:
        return None
    value = int.from_bytes(data, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


def compress(point: Point) -> bytes:
    z = _inv(point[2])
    x, y = point[0] * z % P, point[1] * z % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


G_Y = 4 * _inv(5) % P
G: Point = (_recover_x(G_Y, 0), G_Y, 1, _recover_x(G_Y, 0) * G_Y % P)


def in_prime_order_subgroup(point: Point) -> bool:
    """Require a non-identity point of order L, including for key images."""
    identity = compress(IDENTITY)
    return compress(point) != identity and compress(scalar_mul(point, L)) == identity


def hash_to_scalar(*chunks: bytes) -> int:
    digest = hashlib.sha512(DOMAIN + b"|s|" + b"|".join(chunks)).digest()
    return int.from_bytes(digest, "little") % L


def hash_to_point(*chunks: bytes) -> Point:
    """Try-and-increment: a curve point whose discrete log nobody knows."""
    seed = DOMAIN + b"|p|" + b"|".join(chunks)
    for counter in range(256):
        candidate = hashlib.sha512(seed + counter.to_bytes(4, "little")).digest()[:32]
        point = decompress(candidate)
        if point is None:
            continue
        cleared = scalar_mul(point_double(point_double(point_double(point))), 1)
        if compress(cleared) == compress(IDENTITY):
            continue
        return cleared
    raise RuntimeError("hash_to_point exhausted its counter")  # pragma: no cover


def secret_from_seed(seed: bytes) -> int:
    """A uniform scalar from arbitrary key material, clamped into [1, L)."""
    value = int.from_bytes(hashlib.sha512(DOMAIN + b"|k|" + seed).digest(), "little") % L
    return value or 1


def public_key(secret: int) -> bytes:
    if not 0 < secret < L:
        raise ValueError("secret must be a non-zero canonical scalar")
    return compress(scalar_mul(G, secret))


def key_image(scope: str, secret: int) -> bytes:
    """The nullifier. Deterministic per (scope, key); reveals neither."""
    point = hash_to_point(scope.encode(), public_key(secret))
    return compress(scalar_mul(point, secret))


def sign(scope: str, message: bytes, secret: int, ring: Sequence[bytes]) -> dict[str, object]:
    """Prove membership of `ring` for `scope` without revealing which member."""
    own = public_key(secret)
    if own not in ring:
        raise ValueError("the signing key is not in the ring")
    members = [decompress(item) for item in ring]
    if any(member is None or not in_prime_order_subgroup(member) for member in members):
        raise ValueError("the ring contains an invalid prime-order public key")
    if len(set(ring)) != len(ring):
        raise ValueError("the ring contains duplicate public keys")
    index = list(ring).index(own)
    size = len(ring)
    image = key_image(scope, secret)
    image_point = decompress(image)
    assert image_point is not None

    alpha = secrets.randbelow(L - 1) + 1
    responses = [0] * size
    challenges = [0] * size
    own_hash_point = hash_to_point(scope.encode(), own)

    left = compress(scalar_mul(G, alpha))
    right = compress(scalar_mul(own_hash_point, alpha))
    cursor = (index + 1) % size
    challenges[cursor] = hash_to_scalar(scope.encode(), message, image, left, right)

    while cursor != index:
        responses[cursor] = secrets.randbelow(L - 1) + 1
        member = members[cursor]
        assert member is not None
        member_hash_point = hash_to_point(scope.encode(), ring[cursor])
        left = compress(point_add(scalar_mul(G, responses[cursor]),
                                  scalar_mul(member, challenges[cursor])))
        right = compress(point_add(scalar_mul(member_hash_point, responses[cursor]),
                                   scalar_mul(image_point, challenges[cursor])))
        nxt = (cursor + 1) % size
        challenges[nxt] = hash_to_scalar(scope.encode(), message, image, left, right)
        cursor = nxt

    responses[index] = (alpha - challenges[index] * secret) % L
    return {
        "algorithm": "lsag-ed25519",
        "scope": scope,
        "key_image": image.hex(),
        "challenge": format(challenges[0], "064x"),
        "responses": [format(value, "064x") for value in responses],
        "ring": [item.hex() for item in ring],
    }


def verify(message: bytes, proof: dict[str, object]) -> bool:
    """Recompute the challenge ring; it closes only if a member signed."""
    try:
        if proof.get("algorithm") != "lsag-ed25519":
            return False
        scope = str(proof["scope"])
        image = bytes.fromhex(str(proof["key_image"]))
        challenge = int(str(proof["challenge"]), 16)
        responses = [int(str(value), 16) for value in proof["responses"]]  # type: ignore[union-attr]
        ring = [bytes.fromhex(str(item)) for item in proof["ring"]]  # type: ignore[union-attr]
    except (KeyError, ValueError, TypeError):
        return False
    if not ring or len(responses) != len(ring) or len(set(ring)) != len(ring):
        return False
    if challenge <= 0 or challenge >= L or any(value <= 0 or value >= L for value in responses):
        return False
    image_point = decompress(image)
    if image_point is None or not in_prime_order_subgroup(image_point):
        return False
    members = []
    for item in ring:
        member = decompress(item)
        if member is None or not in_prime_order_subgroup(member):
            return False
        members.append(member)

    current = challenge
    for index in range(len(ring)):
        member_hash_point = hash_to_point(scope.encode(), ring[index])
        left = compress(point_add(scalar_mul(G, responses[index]),
                                  scalar_mul(members[index], current)))
        right = compress(point_add(scalar_mul(member_hash_point, responses[index]),
                                   scalar_mul(image_point, current)))
        current = hash_to_scalar(scope.encode(), message, image, left, right)
    return current == challenge
