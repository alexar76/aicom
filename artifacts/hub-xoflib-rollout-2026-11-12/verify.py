"""Exercise the installed SHAKE backend and the ML-DSA-65 path on a disposable key."""

import concurrent.futures
import hashlib
import importlib.metadata as metadata

import aimarket_hub
import dilithium_py.ml_dsa.ml_dsa as implementation
import xoflib
from dilithium_py.ml_dsa import ML_DSA_65


assert aimarket_hub.__version__ == "3.21.0"
assert metadata.version("xoflib") == "0.4.0"
assert implementation.shake256 is xoflib.shake256

for shake, reference in ((xoflib.shake128, hashlib.shake_128), (implementation.shake256, hashlib.shake_256)):
    first = shake(b"first stream")
    second = shake(b"second stream")
    first_part = first.read(11)
    second_part = second.read(29)
    assert first_part + first.read(179) == reference(b"first stream").digest(190)
    assert second_part + second.read(173) == reference(b"second stream").digest(202)

public_key, private_key = ML_DSA_65.key_derive(bytes(range(32)))


def round_trip(number):
    message = f"concurrent SHAKE probe {number}".encode()
    signature = ML_DSA_65.sign(private_key, message, deterministic=True)
    assert ML_DSA_65.verify(public_key, message, signature)
    assert not ML_DSA_65.verify(public_key, message + b"!", signature)


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(round_trip, range(8)))

print(f"Hub 3.21.0, dilithium-py {metadata.version('dilithium-py')}, xoflib 0.4.0: "
      "independent SHAKE-128/256 streams and eight concurrent ML-DSA-65 round trips passed")
