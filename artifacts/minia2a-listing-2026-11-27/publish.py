"""List ModelMarket's x402 routes on the minia2a.uk marketplace (third-party listing, 0% fee, buyers pay our payTo).

    python3 publish.py              # dry run: checks every listing against minia2a's rules, prints the payloads
    python3 publish.py --send       # signs "minia2a publish: <wallet>" with the payTo key and POSTs each listing

Rules checked (minia2a publish-standard.md, read 2026-11-27): wallet == payTo in our own 402; unpaid POST answers 402
with accepts[] before any parameter check; price_cents integer 1..10000 and equal to our 402 amount (6-decimal USDC
units / 10,000); description 20 chars..480 UTF-8 bytes and names the method; https endpoint.
The key is read only with --send, from ~/.aicom-base-deployer-v4.json (the account whose address equals WALLET); the
script never prints it. Signing a message moves no funds.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WALLET = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"  # payTo of every ModelMarket x402 route on Base
PUBLISH = "https://minia2a.uk/api/v1/publish-service"

LISTINGS = [
    {
        "name": "AIMarket nearby sensors",
        "endpoint": "https://modelmarket.dev/x402/nearby-sensors",
        "price_cents": 3,
        "category": "data",
        "subcategory": "geo-sensors",
        "description": (
            "The nearest live public sensors to a point, one per layer you ask for (weather, air, radiation, quake): "
            "each with its reading, distance and source, plus the hub's signed receipt. Method: POST, JSON body "
            '{"latitude":35.68,"longitude":139.69,"layers":["weather","air"]}. '
            "Pays 0.03 USDC on Base to the payTo in the endpoint's own 402."
        ),
    },
]


def probe(url):
    req = urllib.request.Request(url, data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "aimarket-listing-check"})
    try:
        urllib.request.urlopen(req, timeout=30)
        return 200, None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, None


def check(item):
    problems = []
    size = len(item["description"].encode("utf-8"))
    if not 20 <= len(item["description"]) or size > 480:
        problems.append(f"description is {size} bytes (max 480)")
    if "Method: POST" not in item["description"] and "Method: GET" not in item["description"]:
        problems.append("description does not name the method")
    if not item["endpoint"].startswith("https://"):
        problems.append("endpoint is not https")
    if not (isinstance(item["price_cents"], int) and 1 <= item["price_cents"] <= 10000):
        problems.append("price_cents must be an integer 1..10000")
    status, body = probe(item["endpoint"])
    accepts = (body or {}).get("accepts") or []
    if status != 402 or not accepts:
        problems.append(f"unpaid POST answered {status} without accepts[]")
    else:
        offer = accepts[0]
        if str(offer.get("payTo", "")).lower() != WALLET.lower():
            problems.append(f"402 payTo {offer.get('payTo')} is not WALLET")
        amount = int(offer.get("amount") or offer.get("maxAmountRequired") or 0)
        if amount != item["price_cents"] * 10_000:
            problems.append(f"402 asks {amount} units, listing says {item['price_cents']} cents")
    return size, problems


def signer():
    from eth_account import Account
    from eth_account.messages import encode_defunct
    data = json.loads(Path(os.path.expanduser("~/.aicom-base-deployer-v4.json")).read_text())
    candidates = []
    for entry in data.get("accounts", []):
        if isinstance(entry, dict):
            for key in ("private_key", "privateKey", "key", "secret"):
                if entry.get(key):
                    candidates.append(Account.from_key(entry[key]))
    if not candidates and data.get("mnemonic"):
        Account.enable_unaudited_hdwallet_features()
        candidates = [Account.from_mnemonic(data["mnemonic"], account_path=f"m/44'/60'/0'/0/{i}") for i in range(10)]
    for account in candidates:
        if account.address.lower() == WALLET.lower():
            return lambda text: account.sign_message(encode_defunct(text=text)).signature.to_0x_hex()
    sys.exit("no account in the key file has the payTo address; nothing signed")


def main():
    ok = True
    for item in LISTINGS:
        size, problems = check(item)
        print(f"{item['name']}: description {size} bytes;", "OK" if not problems else "PROBLEMS: " + "; ".join(problems))
        ok = ok and not problems
    if "--send" not in sys.argv:
        print(json.dumps([{**i, "wallet": WALLET, "signature": "<signed with --send>"} for i in LISTINGS], indent=1))
        sys.exit("dry run, nothing signed or sent" if ok else "dry run: fix the problems first")
    if not ok:
        sys.exit("refusing to send: fix the problems first")
    sign = signer()
    signature = sign("minia2a publish: " + WALLET)
    results = []
    for item in LISTINGS:
        payload = json.dumps({**item, "wallet": WALLET, "signature": signature}).encode()
        req = urllib.request.Request(PUBLISH, data=payload, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "aimarket-listing"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                answer = {"status": r.status, "body": json.loads(r.read() or b"null")}
        except urllib.error.HTTPError as e:
            answer = {"status": e.code, "body": e.read().decode(errors="replace")[:500]}
        print(item["name"], answer)
        results.append({"name": item["name"], **answer})
    (HERE / "publish-response.json").write_text(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main()
