"""Inside the overlay image, no network: the new parser file is in place, reads PriorSeal's resources[] items
(0 of 4 before the fix) and still reads oracleinsight's document, and the app imports."""
import hashlib, json, pathlib
import aimarket_hub.observed_sellers as os_mod
src = pathlib.Path(os_mod.__file__).read_bytes()
assert hashlib.sha256(src).hexdigest() == "b1104ce8131d696eee3e4f836bd7442a6c01c35fcd3ccae1000ce691476ca79f", "wrong file"
ps = os_mod.parse_discovery(json.load(open("/tmp/priorseal-x402.json")), "https://priorseal.xyz")
oi = os_mod.parse_discovery(json.load(open("/tmp/oracleinsight-x402.json")), "https://www.oracleinsight.xyz")
print("priorseal routes", len(ps), [r["method"] for r in ps])
print("oracleinsight routes", len(oi))
assert len(ps) == 4 and all(r["method"] == "GET" for r in ps)
assert len(oi) >= 20
import aimarket_hub.api  # noqa: F401  the app still imports with the new module
print("smoke ok")
