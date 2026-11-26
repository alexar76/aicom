"""Registrable domain by the Public Suffix List (ICANN + private sections), minimal matcher."""
import functools

def load(path):
    exact, wild, exc = set(), set(), set()
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        rule = line.split()[0]
        if rule.startswith("!"):
            exc.add(rule[1:])
        elif rule.startswith("*."):
            wild.add(rule[2:])
        else:
            exact.add(rule)
    return exact, wild, exc

def make(path):
    exact, wild, exc = load(path)

    @functools.lru_cache(maxsize=None)
    def registrable(host):
        for sep in "/?#":                      # a host cut from a URL may still carry a query
            host = host.split(sep)[0]
        host = host.rsplit("@", 1)[-1].split(":")[0].strip(".").lower()
        try:
            host = host.encode("idna").decode("ascii") if not host.isascii() else host
        except Exception:
            pass
        labels = host.split(".")
        if all(l.isdigit() for l in labels):
            return host  # IPv4 literal
        n = len(labels)
        suffix_len = 1  # default rule "*"
        for i in range(n):
            cand = ".".join(labels[i:])
            if cand in exc:
                suffix_len = n - i - 1
                break
            if cand in exact:
                suffix_len = max(suffix_len, n - i)
            if i + 1 < n and ".".join(labels[i + 1:]) in wild:
                suffix_len = max(suffix_len, n - i)
        if suffix_len >= n:
            return host
        return ".".join(labels[n - suffix_len - 1:])
    return registrable
