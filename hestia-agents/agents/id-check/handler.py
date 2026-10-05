"""Is this identifier well-formed, or is it a typo? Check digits, checksums and lengths.

Covers identifiers that name accounts, products, publications, securities, companies and
wallets — never people: no payment cards (a card number is the holder's secret, and a hub
refuses it as PII before it would arrive), no national IDs.

  iban      ISO 13616: the country's length (89 countries) and mod 97
  bic       ISO 9362 shape (BIC has no check digit, so only its form can be checked)
  isbn      ISBN-10 (mod 11, X) and ISBN-13; an ISBN-10 also gets its ISBN-13 form
  gtin      EAN-8, UPC-A (GTIN-12), EAN-13 (GTIN-13), GTIN-14: mod 10, weights 3/1
  issn      mod 11, X
  isin      ISO 6166: country prefix, Luhn over the digit expansion (which misses some
            letter swaps: US0378331005 and ES0378331005 both check out)
  lei       ISO 17442: 20 characters, mod 97
  evm       a 20-byte address; mixed case must carry a correct EIP-55 checksum
  bitcoin   Base58Check (P2PKH, P2SH) and Bech32 / Bech32m segwit (BIP 173 / 350)

The type is detected when not given. A check digit catches every single-character error
and most swaps; it cannot tell a typo that happens to check out from the real thing.
"""

import hashlib
import re

MAX_IDS = 1000

IBAN_LENGTHS = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22, "BH": 22,
    "BI": 27, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22, "DJ": 27,
    "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18, "FK": 18, "FO": 18, "FR": 27,
    "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HN": 28, "HR": 21, "HU": 28,
    "IE": 22, "IL": 23, "IQ": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28,
    "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "LY": 25, "MC": 27, "MD": 24, "ME": 22,
    "MK": 19, "MN": 20, "MR": 27, "MT": 31, "MU": 30, "NI": 28, "NL": 18, "NO": 15, "OM": 23,
    "PK": 24, "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "RU": 33, "SA": 24,
    "SC": 31, "SD": 18, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "SO": 23, "ST": 25, "SV": 28,
    "TL": 23, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20, "YE": 30,
}

# ------------------------------------------------------------------ keccak256 (EIP-55)

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_RHO = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56],
        [27, 20, 39, 8, 14]]
_STEPS = [(x + 5 * y, y + 5 * ((2 * x + 3 * y) % 5), _RHO[x][y])
          for x in range(5) for y in range(5)]


def _keccak_f(a):
    m = (1 << 64) - 1
    for rc in _RC:
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x + 4) % 5] ^ (((c[(x + 1) % 5] << 1) | (c[(x + 1) % 5] >> 63)) & m)
             for x in range(5)]
        b = [0] * 25
        for src, dst, r in _STEPS:
            v = a[src] ^ d[src % 5]
            b[dst] = (((v << r) | (v >> (64 - r))) & m) if r else v
        for y in (0, 5, 10, 15, 20):
            for x in range(5):
                a[y + x] = b[y + x] ^ (~b[y + (x + 1) % 5] & b[y + (x + 2) % 5])
        a[0] ^= rc


def keccak256(data):
    state = [0] * 25
    padded = bytearray(data) + b"\x01"
    while len(padded) % 136:
        padded.append(0)
    padded[-1] ^= 0x80
    for off in range(0, len(padded), 136):
        for i in range(17):
            state[i] ^= int.from_bytes(padded[off + 8 * i:off + 8 * i + 8], "little")
        _keccak_f(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(4))


# ------------------------------------------------------------------ helpers


def _alnum_value(text):
    """Letters as numbers (A=10 ... Z=35), digits as themselves: the ISO 7064 expansion."""
    return "".join(str(int(c, 36)) for c in text)


def _mod10_weighted(digits):
    """GTIN check digit for the digits before it: weights 3, 1, 3, ... from the right."""
    total = 0
    for i, d in enumerate(reversed(digits)):
        total += int(d) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10


def _luhn_ok(digits):
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _result(id_type, valid, normalized, reason, **extra):
    out = {"type": id_type, "valid": valid, "normalized": normalized, "reason": reason}
    out.update(extra)
    return out


# ------------------------------------------------------------------ checkers


def check_iban(raw):
    text = re.sub(r"[\s-]", "", raw).upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}", text):
        return _result("iban", False, text, "not an IBAN: two letters, two digits, then up to "
                       "30 letters and digits")
    country = text[:2]
    expected = IBAN_LENGTHS.get(country)
    if expected is None:
        return _result("iban", False, text, country + " does not issue IBANs", country=country)
    if len(text) != expected:
        return _result("iban", False, text, country + " IBANs have " + str(expected)
                       + " characters, this has " + str(len(text)), country=country)
    if int(_alnum_value(text[4:] + text[:4])) % 97 != 1:
        return _result("iban", False, text, "check digits do not match: a typo", country=country)
    # No grouped print form and no bare BBAN in the answer: "DE89 3704 0044 0532 0130 00" holds
    # four groups of four digits that pass the card checksum, and a hub's PII gate refuses the
    # whole answer for it. The compact form is safe — its digits are glued to the country code.
    return _result("iban", True, text, "length and check digits are right", country=country,
                   check_digits=text[2:4])


def check_bic(raw):
    text = raw.strip().upper()
    if not re.fullmatch(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?", text):
        return _result("bic", False, text, "not a BIC: 4 letters (bank), 2 letters (country), "
                       "2 letters/digits (location), optional 3 (branch)")
    return _result("bic", True, text, "well-formed; a BIC has no check digit, so a typo that "
                   "keeps the form passes", bank=text[:4], country=text[4:6],
                   location=text[6:8], branch=text[8:] or "XXX", test_bic=text[7] == "0")


def check_isbn(raw):
    text = re.sub(r"[\s-]", "", raw).upper()
    if text.startswith("ISBN"):
        text = text[4:].lstrip(":")
    if re.fullmatch(r"[0-9]{9}[0-9X]", text):
        total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(text))
        if total % 11:
            return _result("isbn", False, text, "ISBN-10 check digit does not match: a typo")
        isbn13 = "978" + text[:9]
        isbn13 += str(_mod10_weighted(isbn13))
        return _result("isbn", True, text, "ISBN-10 check digit is right", isbn13=isbn13)
    if re.fullmatch(r"97[89][0-9]{10}", text):
        if _mod10_weighted(text[:12]) != int(text[12]):
            return _result("isbn", False, text, "ISBN-13 check digit does not match: a typo")
        return _result("isbn", True, text, "ISBN-13 check digit is right")
    return _result("isbn", False, text, "not an ISBN: 10 characters (last may be X) or 13 "
                   "digits starting 978/979")


_GTIN_KINDS = {8: "EAN-8", 12: "UPC-A (GTIN-12)", 13: "EAN-13 (GTIN-13)", 14: "GTIN-14"}


def check_gtin(raw):
    text = re.sub(r"[\s-]", "", raw)
    if not text.isdigit() or len(text) not in _GTIN_KINDS:
        return _result("gtin", False, text, "not a GTIN: 8, 12, 13 or 14 digits")
    kind = _GTIN_KINDS[len(text)]
    if _mod10_weighted(text[:-1]) != int(text[-1]):
        return _result("gtin", False, text, kind + " check digit does not match: a typo",
                       kind=kind)
    return _result("gtin", True, text, kind + " check digit is right", kind=kind,
                   gtin14=text.rjust(14, "0"))


def check_issn(raw):
    text = re.sub(r"[\s-]", "", raw).upper()
    if text.startswith("ISSN"):
        text = text[4:].lstrip(":")
    if not re.fullmatch(r"[0-9]{7}[0-9X]", text):
        return _result("issn", False, text, "not an ISSN: 7 digits and a check character")
    total = sum((8 - i) * int(c) for i, c in enumerate(text[:7]))
    check = (11 - total % 11) % 11
    if ("X" if check == 10 else str(check)) != text[7]:
        return _result("issn", False, text, "check character does not match: a typo")
    return _result("issn", True, text, "check character is right",
                   print_format=text[:4] + "-" + text[4:])


def check_isin(raw):
    text = raw.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", text):
        return _result("isin", False, text, "not an ISIN: 2 letters, 9 letters/digits, a digit")
    if not _luhn_ok(_alnum_value(text)):
        return _result("isin", False, text, "check digit does not match: a typo",
                       country=text[:2])
    return _result("isin", True, text, "check digit is right", country=text[:2],
                   nsin=text[2:11])


def check_lei(raw):
    text = re.sub(r"\s", "", raw).upper()
    if not re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", text):
        return _result("lei", False, text, "not an LEI: 18 letters/digits and 2 check digits")
    if int(_alnum_value(text)) % 97 != 1:
        return _result("lei", False, text, "check digits do not match: a typo")
    return _result("lei", True, text, "check digits are right", lou=text[:4])


def _eip55(lower):
    digest = keccak256(lower.encode("ascii")).hex()
    return "0x" + "".join(c.upper() if c.isalpha() and int(digest[i], 16) >= 8 else c
                          for i, c in enumerate(lower))


def check_evm(raw):
    text = raw.strip()
    if not re.fullmatch(r"0[xX][0-9a-fA-F]{40}", text):
        return _result("evm", False, text, "not an EVM address: 0x and 40 hex digits")
    body = text[2:]
    checksummed = _eip55(body.lower())
    if body == body.lower() or body == body.upper():
        return _result("evm", True, checksummed, "well-formed; single-case addresses carry no "
                       "checksum, so a typo here is not detectable", checksum=False)
    if "0x" + body != checksummed:
        # Never hand back a "corrected" form: re-checksumming a typo makes a wrong address look
        # right.
        return _result("evm", False, text, "EIP-55 checksum does not match: a typo (or a "
                       "hand-edited address)", checksum=True)
    return _result("evm", True, checksummed, "EIP-55 checksum is right", checksum=True)


# ------------------------------------------------------------------ bitcoin

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32M_CONST = 0x2BC830A3
_B58_VERSIONS = {0x00: ("mainnet", "p2pkh"), 0x05: ("mainnet", "p2sh"),
                 0x6F: ("testnet", "p2pkh"), 0xC4: ("testnet", "p2sh")}
_HRPS = {"bc": "mainnet", "tb": "testnet", "bcrt": "regtest"}


def _polymod(values):
    gen = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            chk ^= gen[i] if (top >> i) & 1 else 0
    return chk


def _expand(hrp):
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _convert(data, frm, to):
    acc, bits, out, maxv = 0, 0, [], (1 << to) - 1
    for value in data:
        acc = (acc << frm) | value
        bits += frm
        while bits >= to:
            bits -= to
            out.append((acc >> bits) & maxv)
    if bits >= frm or (acc << (to - bits)) & maxv:
        return None
    return out


def _segwit(text):
    if text != text.lower() and text != text.upper():
        return _result("bitcoin", False, text, "mixed case: bech32 addresses are one case")
    low = text.lower()
    pos = low.rfind("1")
    if pos < 1 or pos + 7 > len(low) or len(low) > 90:
        return _result("bitcoin", False, low, "not a bech32 string (separator or length)")
    hrp, data_part = low[:pos], low[pos + 1:]
    if hrp not in _HRPS:
        return _result("bitcoin", False, low, "'" + hrp + "' is not a bitcoin prefix (bc, tb, "
                       "bcrt)")
    if any(c not in _BECH32 for c in data_part):
        return _result("bitcoin", False, low, "a character outside the bech32 alphabet")
    data = [_BECH32.find(c) for c in data_part]
    if len(data) < 7:
        return _result("bitcoin", False, low, "empty data section")
    const = _polymod(_expand(hrp) + data)
    version = data[0]
    if version > 16:
        return _result("bitcoin", False, low, "witness version above 16")
    wanted = 1 if version == 0 else _BECH32M_CONST
    if const != wanted:
        if const in (1, _BECH32M_CONST):
            return _result("bitcoin", False, low, "checksum is " + ("Bech32" if const == 1 else
                           "Bech32m") + " but witness version " + str(version) + " needs "
                           + ("Bech32" if version == 0 else "Bech32m"))
        return _result("bitcoin", False, low, "checksum does not match: a typo")
    program = _convert(data[1:-6], 5, 8)
    if program is None:
        return _result("bitcoin", False, low, "bad padding in the witness program")
    if not 2 <= len(program) <= 40:
        return _result("bitcoin", False, low, "witness program of " + str(len(program))
                       + " bytes (2 to 40 allowed)")
    if version == 0 and len(program) not in (20, 32):
        return _result("bitcoin", False, low, "version 0 programs are 20 or 32 bytes")
    kind = {(0, 20): "p2wpkh", (0, 32): "p2wsh", (1, 32): "p2tr"}.get(
        (version, len(program)), "witness v" + str(version))
    script = bytes([version + 0x50 if version else 0, len(program)]) + bytes(program)
    return _result("bitcoin", True, low, "checksum and program are right", network=_HRPS[hrp],
                   kind=kind, witness_version=version, script_pubkey=script.hex())


def check_bitcoin(raw):
    text = raw.strip()
    if re.match(r"(bc|tb|bcrt)1", text, re.IGNORECASE):
        return _segwit(text)
    if not text or any(c not in _B58 for c in text):
        return _result("bitcoin", False, text, "not base58 and not bech32")
    number = 0
    for c in text:
        number = number * 58 + _B58.find(c)
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    raw_bytes = b"\x00" * (len(text) - len(text.lstrip("1"))) + body
    if len(raw_bytes) != 25:
        return _result("bitcoin", False, text, "decodes to " + str(len(raw_bytes))
                       + " bytes, not 25")
    payload, checksum = raw_bytes[:21], raw_bytes[21:]
    if hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != checksum:
        return _result("bitcoin", False, text, "Base58Check checksum does not match: a typo")
    if payload[0] not in _B58_VERSIONS:
        return _result("bitcoin", False, text, "version byte " + str(payload[0])
                       + " is not a bitcoin address")
    network, kind = _B58_VERSIONS[payload[0]]
    return _result("bitcoin", True, text, "Base58Check checksum is right", network=network,
                   kind=kind, hash160=payload[1:].hex())


CHECKERS = {"iban": check_iban, "bic": check_bic, "isbn": check_isbn, "gtin": check_gtin,
            "issn": check_issn, "isin": check_isin, "lei": check_lei, "evm": check_evm,
            "bitcoin": check_bitcoin}


def detect(raw):
    text = raw.strip()
    compact = re.sub(r"[\s-]", "", text).upper()
    if re.fullmatch(r"0[xX][0-9a-fA-F]{40}", text):
        return "evm"
    if re.match(r"(bc|tb|bcrt)1", text, re.IGNORECASE) or re.fullmatch(
            r"[13mn2][1-9A-HJ-NP-Za-km-z]{25,34}", text):
        return "bitcoin"
    if re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", compact) and compact[:2] in IBAN_LENGTHS:
        return "iban"
    if re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", compact):
        return "lei"
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", compact):
        return "isin"
    if compact.startswith("ISSN") or re.fullmatch(r"[0-9]{4}-[0-9]{3}[0-9Xx]", text):
        return "issn"
    if compact.startswith("ISBN") or re.fullmatch(r"97[89][0-9]{10}|[0-9]{9}[0-9X]", compact):
        return "isbn"
    if compact.isdigit() and len(compact) in _GTIN_KINDS:
        return "gtin"
    if re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?", compact):
        return "bic"
    if re.fullmatch(r"[0-9]{7}[0-9X]", compact):
        return "issn"
    return None


def _one(item, default_type):
    kind = default_type
    raw = item
    if isinstance(item, dict):
        raw, kind = item.get("id"), item.get("type", default_type)
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 120:
        raise ValueError("each id must be a non-empty string of at most 120 characters")
    kind = kind or detect(raw)
    if kind is None:
        out = {"type": None, "valid": False, "normalized": raw.strip(),
               "reason": "not a recognised identifier; send 'type' (" + ", ".join(CHECKERS) + ")"}
    elif kind not in CHECKERS:
        raise ValueError("type must be one of " + ", ".join(CHECKERS))
    else:
        out = CHECKERS[kind](raw)
    out["input"] = raw
    return out


def handle(payload):
    default_type = payload.get("type")
    if default_type is not None and default_type not in CHECKERS:
        raise ValueError("type must be one of " + ", ".join(CHECKERS))
    if "ids" in payload:
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids:
            raise ValueError("ids must be a non-empty list")
        if len(ids) > MAX_IDS:
            raise ValueError("at most " + str(MAX_IDS) + " ids per call")
        results = [_one(i, default_type) for i in ids]
        return {"results": results, "valid": sum(1 for r in results if r["valid"]),
                "invalid": sum(1 for r in results if not r["valid"])}
    if "id" not in payload:
        raise ValueError("send 'id' (one identifier) or 'ids' (a list)")
    return _one(payload.get("id"), default_type)
