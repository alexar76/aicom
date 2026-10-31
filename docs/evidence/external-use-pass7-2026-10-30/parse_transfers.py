"""Parse saved public BaseScan token tables, without network access."""
from collections import Counter
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
PAYER = "0xe2d8dc842fc5037c99c332bd57baaba3649f66c2"
OPERATOR = "0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a"

class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.current = {"text": [], "links": []}
        if tag == "a" and self.current is not None:
            self.current["links"].extend(value for key, value in attrs if key == "href")

    def handle_data(self, value):
        if self.current is not None and value.strip():
            self.current["text"].append(value.strip())

    def handle_endtag(self, tag):
        if tag == "tr" and self.current is not None:
            self.rows.append(self.current)
            self.current = None

def parse(name, wallet):
    parser = Rows()
    parser.feed((ROOT / (name + ".raw")).read_text())
    rows = []
    for row in parser.rows:
        txs = [link[4:] for link in row["links"] if re.fullmatch(r"/tx/0x[0-9a-fA-F]{64}", link)]
        if not txs:
            continue
        addresses = [match.group(1).lower() for link in row["links"]
                     for match in [re.match(r"/address/(0x[0-9a-fA-F]{40})", link)] if match]
        directions = [(i, text) for i, text in enumerate(row["text"]) if text in ["IN", "OUT", "SELF"]]
        dates = [text for text in row["text"] if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2}", text)]
        result = {"tx": txs[0], "date_utc": dates[0] if dates else None,
                  "official_base_usdc": any("/token/" + USDC in link.lower() for link in row["links"]),
                  "raw": row}
        if len(directions) == 1 and len(addresses) == 1:
            i, direction = directions[0]
            result.update(direction=direction, counterparty=addresses[0],
                          payer=wallet if direction == "OUT" else addresses[0],
                          recipient=addresses[0] if direction == "OUT" else wallet)
            try:
                result["amount_usdc"] = str(Decimal(row["text"][i + 2].replace(",", "")))
            except (InvalidOperation, IndexError):
                result["parse_amount_error"] = True
        rows.append(result)
    return rows

operator_rows = parse("base-wallet-transfers", OPERATOR)
payer_rows = parse("unattributed-payer-transfers", PAYER)
payments = [row for row in operator_rows if row.get("payer") == PAYER and row["official_base_usdc"]]
outbound = [row for row in payer_rows if row.get("direction") == "OUT" and row["official_base_usdc"]]
by_day = Counter(row["date_utc"].split()[0] for row in outbound)
recipients = Counter(row["recipient"] for row in outbound)
out = {"candidate_address": PAYER, "operator_address": OPERATOR,
       "operator_table_rows": len(operator_rows), "operator_table_matches": payments,
       "payer_table_rows": len(payer_rows), "outbound_official_usdc_rows": len(outbound),
       "unique_outbound_recipients": len(recipients),
       "singleton_recipient_count": sum(count == 1 for count in recipients.values()),
       "outbound_by_day": dict(by_day),
       "outbound_amounts": dict(Counter(row.get("amount_usdc", "unparsed") for row in outbound)),
       "payer_rows": payer_rows,
       "limits": ["One 50-row page per address, not full lifetime history", "Token table is explorer evidence; detailed transaction separately captured", "Payments do not reveal HTTP endpoint, task, delivered result or beneficial owner", "Sampling-like distribution is descriptive and does not establish intent"]}
(ROOT / "payer-attribution.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({key: value for key, value in out.items() if key not in ["payer_rows", "operator_table_matches"]}, indent=2))
print(json.dumps({"payments": [{key: value for key, value in row.items() if key != "raw"} for row in payments]}, indent=2))
