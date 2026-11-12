set -eu
registry=https://modelmarket.dev/ard/v1
curl -fsS "$registry/search" \
  -H 'Content-Type: application/json' \
  --data '{"query":{"text":"weather","filter":{"publisher":"modelmarket.dev"}},"pageSize":10}' |
python3 -c '
import json, sys
fields = ("identifier", "type", "version", "digest")
row = next(r for r in json.load(sys.stdin)["results"]
           if r.get("trustManifest"))

def bound(result):
    coordinates = {k: result[k] for k in fields if k in result}
    return result["trustManifest"]["subject"] == coordinates

print("current:", bound(row))
del row["version"]
print("without version:", bound(row))
'
