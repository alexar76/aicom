"""Does this name pretend to be another one? Look-alike characters, mixed scripts, invisible
and bidirectional controls, compatibility forms and punycode, for agent names, tool names,
package names and domains.

  mixed script        Latin with Cyrillic or Greek in one name ("pаypal" with a Cyrillic а);
                      the Japanese, Korean and Chinese mixes UTS #39 allows are not flagged
  whole-script        a name written entirely in another script that reads as Latin ("аррӏе")
  confusable_with     same skeleton as a name you protect (`against`), but not that name
  invisible / bidi    zero-width, tag and variation characters; bidi controls (Trojan Source)
  compatibility       fullwidth, mathematical or ligature forms NFKC folds away
  punycode            xn-- labels decoded before any of the above (`kind: domain`)

The skeleton follows UTS #39 (NFKC, then each character to its prototype, case folded),
with a curated table of the Latin look-alikes that real spoofs use — not the full
confusables.txt, which would not fit here. It answers "looks like", never "is malicious".
"""

import unicodedata

MAX_TEXTS = 500
MAX_LEN = 253

# Prototype per character, applied BEFORE case folding so capitals keep their look-alikes.
_PROTO = {}
for _src, _dst in (
    # Cyrillic
    ("аА", "a"), ("вВ", "b"), ("еЕёЁ", "e"), ("іІӀ", "i"), ("јЈ", "j"), ("кК", "k"),
    ("М", "m"), ("Н", "h"), ("оО", "o"), ("рР", "p"), ("сС", "c"), ("Т", "t"), ("уУ", "y"),
    ("хХ", "x"), ("ѕЅ", "s"), ("ԁ", "d"), ("ԛ", "q"), ("ԝԜ", "w"), ("һ", "h"), ("ӏ", "l"),
    ("ү", "y"), ("ѵ", "v"), ("ԍ", "g"), ("Ү", "y"), ("Ԁ", "d"), ("ɡ", "g"),
    # Greek
    ("αΑ", "a"), ("Β", "b"), ("Ε", "e"), ("Ζ", "z"), ("Η", "h"), ("ιΙ", "i"), ("κΚ", "k"),
    ("Μ", "m"), ("νΝ", "v"), ("οΟ", "o"), ("ρΡ", "p"), ("Τ", "t"), ("υΥ", "y"), ("χΧ", "x"),
    ("γ", "y"), ("ϲϹ", "c"), ("ϳ", "j"),
    # Armenian
    ("օՕ", "o"), ("ս", "u"), ("հ", "h"), ("ո", "n"), ("զ", "q"), ("ց", "g"),
    # Cherokee capitals
    ("Ꭺ", "a"), ("Ᏼ", "b"), ("Ꮯ", "c"), ("Ꭼ", "e"), ("Ꮋ", "h"), ("Ꭻ", "j"), ("Ꮶ", "k"),
    ("Ꮇ", "m"), ("Ꮲ", "p"), ("Ꮪ", "s"), ("Ꭲ", "t"), ("Ꮩ", "v"), ("Ꮃ", "w"), ("Ꮓ", "z"),
    # Latin variants and ASCII look-alikes
    ("ıɩ", "i"), ("ɑ", "a"), ("ʟ", "l"), ("I|", "l"), ("1", "l"), ("0", "o"),
):
    for _c in _src:
        _PROTO[_c] = _dst
_MULTI = (("rn", "m"), ("vv", "w"), ("cl", "d"))

_INVISIBLE = ((0x00AD, 0x00AD, "soft hyphen"), (0x034F, 0x034F, "combining grapheme joiner"),
              (0x115F, 0x1160, "Hangul filler"), (0x180E, 0x180E, "Mongolian vowel separator"),
              (0x200B, 0x200D, "zero-width space/joiner"), (0x2060, 0x2064, "invisible operator"),
              (0x3164, 0x3164, "Hangul filler"), (0xFEFF, 0xFEFF, "zero-width no-break space"),
              (0xFFA0, 0xFFA0, "halfwidth Hangul filler"), (0xFE00, 0xFE0F, "variation selector"),
              (0xE0000, 0xE007F, "tag character"), (0xE0100, 0xE01EF, "variation selector"),
              (0x2800, 0x2800, "braille blank"))
_BIDI = ((0x200E, 0x200F), (0x202A, 0x202E), (0x2066, 0x2069), (0x061C, 0x061C))
# Script mixes UTS #39 "highly restrictive" allows.
_ALLOWED_MIXES = ({"LATIN", "HAN", "HIRAGANA", "KATAKANA"}, {"LATIN", "HAN", "BOPOMOFO"},
                  {"LATIN", "HAN", "HANGUL"})


def _script(char):
    """A character's script, from its Unicode name; None for digits, punctuation and marks."""
    if not unicodedata.category(char).startswith("L"):
        return None
    name = unicodedata.name(char, "")
    first = name.split(" ")[0] if name else "UNKNOWN"
    if first == "CJK" or name.startswith("IDEOGRAPHIC"):
        return "HAN"
    if first == "KATAKANA-HIRAGANA":  # the prolonged sound mark belongs to both kana
        return "KATAKANA"
    if first in ("MODIFIER", "SMALL", "FULLWIDTH", "HALFWIDTH", "MATHEMATICAL", "CIRCLED"):
        rest = name.split(" ")
        return rest[1] if len(rest) > 1 and rest[1] in ("LATIN", "GREEK", "CYRILLIC") else first
    return first


def skeleton(text):
    folded = unicodedata.normalize("NFKC", text)
    visible = (c for c in folded if not _ranges(c, _INVISIBLE) and not _ranges(c, _BIDI))
    out = "".join(_PROTO.get(c, c.casefold()) for c in visible)
    for multi, single in _MULTI:
        out = out.replace(multi, single)
    return out


def _bare(text):
    """The skeleton with every combining mark removed: 'modelmarkét' -> 'modelmarket'."""
    decomposed = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", text))
    return skeleton("".join(c for c in decomposed if not unicodedata.category(c).startswith("M")))


# ------------------------------------------------------------------ punycode (RFC 3492)


def _adapt(delta, points, first):
    delta = delta // 700 if first else delta // 2
    delta += delta // points
    k = 0
    while delta > 455:  # ((36 - 1) * 26) // 2
        delta //= 35
        k += 36
    return k + 36 * delta // (delta + 38)


def punycode_decode(label):
    pos = label.rfind("-")
    output = list(label[:pos]) if pos > 0 else []
    rest = label[pos + 1:] if pos > 0 else label
    if any(ord(c) > 127 for c in output):
        raise ValueError("non-ASCII before the delimiter")
    n, i, bias, k_pos = 128, 0, 72, 0
    while k_pos < len(rest):
        old_i, w, k = i, 1, 36
        while True:
            if k_pos >= len(rest):
                raise ValueError("truncated punycode")
            c = rest[k_pos]
            k_pos += 1
            if "0" <= c <= "9":
                digit = ord(c) - 22
            elif "a" <= c.lower() <= "z":
                digit = ord(c.lower()) - 97
            else:
                raise ValueError("bad punycode digit")
            i += digit * w
            t = 1 if k <= bias else 26 if k >= bias + 26 else k - bias
            if digit < t:
                break
            w *= 36 - t
            k += 36
            if w > 1 << 64:
                raise ValueError("punycode overflow")
        bias = _adapt(i - old_i, len(output) + 1, old_i == 0)
        n += i // (len(output) + 1)
        i %= len(output) + 1
        if n > 0x10FFFF:
            raise ValueError("punycode out of range")
        output.insert(i, chr(n))
        i += 1
    return "".join(output)


# ------------------------------------------------------------------ analysis


def _ranges(char, table):
    point = ord(char)
    for entry in table:
        if entry[0] <= point <= entry[1]:
            return entry
    return None


def _analyse(text, kind, protected):
    issues = []
    shown = text
    if kind == "domain":
        labels = []
        for label in text.lower().rstrip(".").split("."):
            if label.startswith("xn--"):
                try:
                    decoded = punycode_decode(label[4:])
                except ValueError as exc:
                    issues.append({"kind": "punycode", "risk": "high",
                                   "detail": label + ": " + str(exc)})
                    decoded = label
                else:
                    issues.append({"kind": "punycode", "risk": "medium",
                                   "detail": label + " is " + decoded})
                labels.append(decoded)
            else:
                labels.append(label)
        shown = ".".join(labels)
    invisible, bidi = [], []
    for index, char in enumerate(shown):
        hit = _ranges(char, _INVISIBLE)
        if hit:
            invisible.append(str(index) + ": U+" + format(ord(char), "04X") + " " + hit[2])
        if _ranges(char, _BIDI):
            bidi.append(str(index) + ": U+" + format(ord(char), "04X"))
    if invisible:
        issues.append({"kind": "invisible", "risk": "high", "detail": "; ".join(invisible[:10])})
    if bidi:
        issues.append({"kind": "bidi_control", "risk": "high",
                       "detail": "reorders how the text displays: " + "; ".join(bidi[:10])})
    nfkc = unicodedata.normalize("NFKC", shown)
    if nfkc != shown:
        issues.append({"kind": "compatibility", "risk": "medium",
                       "detail": "NFKC folds it to " + nfkc})
    parts = [shown] if kind != "domain" else shown.split(".")
    scripts_all = set()
    for part in parts:
        scripts = {s for s in (_script(c) for c in unicodedata.normalize("NFKC", part)) if s}
        scripts_all |= scripts
        if len(scripts) > 1 and not any(scripts <= allowed for allowed in _ALLOWED_MIXES):
            odd = [c + " (" + str(_script(c)) + ")" for c in part
                   if _script(c) not in (None, "LATIN")][:8]
            issues.append({"kind": "mixed_script", "risk": "high",
                           "detail": part + ": " + ", ".join(sorted(scripts)) + " — "
                           + ", ".join(odd)})
        elif scripts and "LATIN" not in scripts and any(c in _PROTO for c in part):
            letters = [c for c in unicodedata.normalize("NFKC", part)
                       if unicodedata.category(c).startswith("L")]
            if letters and all(c in _PROTO for c in letters):
                issues.append({"kind": "whole_script", "risk": "medium",
                               "detail": part + " is all " + "/".join(sorted(scripts))
                               + " letters that read as Latin: " + skeleton(part)})
    skel = skeleton(shown)
    bare = _bare(shown)
    look_alikes, accent_alikes = [], []
    for name in protected:
        if name == shown:
            continue
        if skeleton(name) == skel:
            look_alikes.append(name)
        elif _bare(name) == bare:
            accent_alikes.append(name)
    if look_alikes:
        issues.append({"kind": "confusable_with", "risk": "high",
                       "detail": "looks like " + ", ".join(look_alikes[:10])})
    if accent_alikes:
        issues.append({"kind": "confusable_ignoring_accents", "risk": "medium",
                       "detail": "differs only by accents from " + ", ".join(accent_alikes[:10])})
    level = "high" if any(i["risk"] == "high" for i in issues) else (
        "medium" if any(i["risk"] == "medium" for i in issues) else "none")
    return {"text": text, "displayed": shown, "skeleton": skel,
            "scripts": sorted(scripts_all), "risk": level, "issues": issues,
            "confusable_with": look_alikes}


def handle(payload):
    kind = payload.get("kind", "identifier")
    if kind not in ("identifier", "domain"):
        raise ValueError("kind must be identifier or domain")
    if "texts" in payload:
        texts = payload.get("texts")
        if not isinstance(texts, list) or not texts:
            raise ValueError("texts must be a non-empty list of strings")
    elif "text" in payload:
        texts = [payload.get("text")]
    else:
        raise ValueError("send 'text' (one name) or 'texts' (a list)")
    if len(texts) > MAX_TEXTS:
        raise ValueError("at most " + str(MAX_TEXTS) + " texts per call")
    protected = payload.get("against", [])
    if not isinstance(protected, list) or len(protected) > MAX_TEXTS:
        raise ValueError("against must be a list of at most " + str(MAX_TEXTS) + " names")
    for value in list(texts) + list(protected):
        if not isinstance(value, str) or not value or len(value) > MAX_LEN:
            raise ValueError("every name must be a string of 1 to " + str(MAX_LEN) + " characters")
    if kind == "domain":
        protected = [p.lower() for p in protected]
    results = [_analyse(t, kind, protected) for t in texts]
    if "text" in payload and "texts" not in payload:
        return results[0]
    return {"results": results,
            "flagged": [r["text"] for r in results if r["risk"] != "none"]}
