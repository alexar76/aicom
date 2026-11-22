"""registry.entry.verify@v1: does this MCP registry entry still hold up against the packages and the
domain it names?

Give `name` (e.g. "io.github.alexar76/warden" or "com.notion/mcp") and optionally `version`
(default: the latest). The agent reads the entry from the official MCP registry, then repeats, as
things stand now, the ownership checks the registry ran when the version was published (registry
source, internal/validators/registries and internal/api/handlers/v0/auth):

  - npm: GET registry.npmjs.org/<identifier>/<version>; package.json `mcpName` must equal the server
    name. Also reported: deprecated, the repository's GitHub owner, npm signatures and whether the
    version has provenance attestations.
  - PyPI: GET pypi.org/pypi/<identifier>/<version>/json; the description (the README) must contain
    "mcp-name: <name>" followed by a boundary: the end, a character that cannot be part of a server
    name, or "-->". Also reported: yanked, the repository's GitHub owner.
  - NuGet: GET api.nuget.org/v3-flatcontainer/<id>/<version>/readme; the same mcp-name rule. With no
    embedded README, the version's existence is checked and the package fails, as there.
  - io.github.<owner>/...: the registry checks this namespace by GitHub login, which nobody can
    re-check later. The agent reports whether server.json's repository and each package's repository
    are under <owner>, as a warning when they are not.
  - a domain namespace (com.example/... or com.example.sub/...): DNS authentication grants a domain
    and its subdomains, so the agent asks dns.google for a well-formed `v=MCPv1;
    k=ed25519|ecdsap384; p=...` TXT record at the namespace's domain, then its parent. HTTP
    authentication grants only the exact domain: give `domain` and the agent also reads
    https://<domain>/.well-known/mcp-registry-auth (no redirects, as the registry).

The verdict follows the registry's own rules only: verified (every package and the domain pass),
verified_partly (nothing failed, something could not be checked: OCI, Cargo, MCPB, or the call's six
requests ran out) or mismatch. Signals beyond those rules (the registry marks the version
deprecated, npm deprecation, a yanked PyPI release, a repository under another owner) are warnings
and do not change the verdict. Remotes are listed, not called.

What a pass means: the markers that tie these packages and this domain to this name are there today.
It says nothing about whether the code is safe, and a key in DNS today does not prove who published
a given version; see package.provenance.verify and warden.scan for those questions.
"""

import base64
import json
import re

REGISTRY = "https://registry.modelcontextprotocol.io"
NPM = "https://registry.npmjs.org"
NUGET = "https://api.nuget.org/v3/index.json"
NUGET_FLAT = "https://api.nuget.org/v3-flatcontainer/"
PYPI = "https://pypi.org"
DNS = "https://dns.google/resolve"
MAX_FETCHES = 6
NAME = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9])/([a-zA-Z0-9._-]+)$")
GITHUB = re.compile(
    r"(?<![A-Za-z0-9-])github\.com[/:]([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)/([A-Za-z0-9._-]+)"
)
# The registry's MCPProofRecordPattern, and every match in a string counts (key rotation).
PROOF = re.compile(r"v=MCPv1;\s*k=([^;]+);\s*p=([A-Za-z0-9+/=]+)")
# Go's url.PathEscape leaves unreserved characters and these sub-delimiters alone.
PATH_SAFE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~$&+,:;=@"
NAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-_/"
P384 = 2**384 - 2**128 - 2**96 + 2**32 - 1
P384_B = int(
    "B3312FA7E23EE7E4988E056BE3F82D19181D9C6EFE8141120314088F5013875A"
    "C656398D8A2ED19D2A85C8EDD3EC2AEF",
    16,
)
NOT_CHECKED = {
    "oci": "the registry reads the io.modelcontextprotocol.server.name label from the image "
    "config, a blob registries serve through a redirect to a CDN host this agent does not reach",
    "cargo": "the registry reads the README crates.io renders on its CDN host, which this agent "
    "does not reach",
    "mcpb": "a release asset behind a redirect; its fileSha256 is not recomputed here",
}


class _Budget(Exception):
    """The call has used the six requests the hearth allows."""


def _path(text):
    out = ""
    for byte in str(text).encode("utf-8"):
        char = chr(byte)
        out += char if char in PATH_SAFE else "%" + format(byte, "02X")
    return out


def _get(state, url, accept="application/json"):
    if state["fetches"] >= MAX_FETCHES:
        raise _Budget()
    state["fetches"] += 1
    return fetch(url, headers={"accept": accept})  # noqa: F821 — the sandbox provides fetch()


def _json(reply):
    if not reply.ok:
        return None
    try:
        return json.loads(reply.text)
    except ValueError:
        return None


def _github_repo(url):
    match = GITHUB.search(str(url or "").strip())
    if not match:
        return None
    repo = match.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    return match.group(1).lower(), repo


def mcp_name_token(content, name):
    """(found, glued_after): the registry's containsMCPNameToken, and what follows the first
    unbounded occurrence when there is no bounded one."""
    content = content or ""
    token = "mcp-name: " + name
    start, first_glued = 0, None
    while True:
        index = content.find(token, start)
        if index < 0:
            return False, first_glued
        rest = content[index + len(token) :]
        if (
            not rest
            or rest[0] not in NAME_CHARS
            or rest.startswith("-->")
            or rest.startswith("--!>")
        ):
            return True, None
        if first_glued is None:
            first_glued = rest[0]
        start = index + 1


def _p384_point(raw):
    """Decompress a P-384 point (02/03 || x); None when it is not on the curve."""
    x = int.from_bytes(raw[1:], "big")
    if x >= P384:
        return None
    rhs = (pow(x, 3, P384) - 3 * x + P384_B) % P384
    y = pow(rhs, (P384 + 1) // 4, P384)
    return (x, y) if y * y % P384 == rhs else None


def proof_keys(text):
    """Every MCPv1 proof record in `text`, parsed as the registry's ParsePublicKey does."""
    keys = []
    for algorithm, encoded in PROOF.findall(text or ""):
        key = {
            "record": "v=MCPv1; k=" + algorithm + "; p=" + encoded,
            "algorithm": algorithm,
            "valid": False,
        }
        keys.append(key)
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            key["problem"] = "p is not standard base64"
            continue
        if algorithm == "ed25519":
            if len(raw) != 32:
                key["problem"] = "an Ed25519 key is 32 bytes, this one is " + str(len(raw))
                continue
        elif algorithm == "ecdsap384":
            if len(raw) != 49 or raw[0] not in (2, 3):
                key["problem"] = "an ecdsap384 key is a 49-byte compressed point (02 or 03 first)"
                continue
            if _p384_point(raw) is None:
                key["problem"] = "the ecdsap384 key is not a point on P-384"
                continue
        else:
            key["problem"] = "k must be ed25519 or ecdsap384"
            continue
        key["valid"] = True
    return keys


def _txt(data):
    """One TXT answer from dns.google (unquoted) or a quoted resolver, as one string."""
    text = str(data or "").strip()
    if text.startswith('"'):
        return "".join(
            part.replace('\\"', '"') for part in re.findall(r'"((?:[^"\\]|\\.)*)"', text)
        )
    return text


def _check(checks, name, ok, detail):
    checks.append({"check": name, "ok": ok, "detail": detail})


def _repo_check(out, url, owner, where):
    """Where a package's repository lives, against an io.github namespace's owner: a warning, since
    the registry does not check it."""
    if not owner:
        return
    got = _github_repo(url)
    if got is None:
        out["repository"] = None
    else:
        out["repository"] = "github.com/" + got[0] + "/" + got[1]
        out["repository_owner_matches"] = got[0] == owner
        if got[0] != owner:
            out["warnings"].append(
                where
                + " is github.com/"
                + got[0]
                + "/"
                + got[1]
                + ", not under the namespace owner "
                + owner
            )


def _npm(state, package, name, owner, out):
    ident, version = out["identifier"], out["version"]
    reply = _get(state, NPM + "/" + _path(ident) + "/" + _path(version))
    doc = _json(reply)
    checks = out["checks"]
    if not isinstance(doc, dict) or doc.get("version") != version:
        _check(
            checks,
            "published",
            False,
            "npm answered HTTP " + str(reply.status) + " for " + ident + "@" + version,
        )
        return
    _check(checks, "published", True, ident + "@" + version + " is on npm")
    marker = doc.get("mcpName")
    if marker == name:
        _check(checks, "mcpName", True, "package.json mcpName is the server name")
    elif not marker:
        _check(checks, "mcpName", False, "package.json has no mcpName")
    else:
        _check(
            checks,
            "mcpName",
            False,
            "package.json mcpName is " + json.dumps(str(marker)) + ", not " + name,
        )
    if doc.get("deprecated"):
        out["warnings"].append("deprecated on npm: " + str(doc["deprecated"])[:200])
    repo = doc.get("repository")
    _repo_check(
        out, repo.get("url") if isinstance(repo, dict) else repo, owner, "package.json repository"
    )
    dist = doc.get("dist") or {}
    out["integrity"] = dist.get("integrity")
    out["npm_registry_signatures"] = len(dist.get("signatures") or [])
    out["has_provenance"] = bool(dist.get("attestations"))


def _pypi(state, package, name, owner, out):
    ident, version = out["identifier"], out["version"]
    reply = _get(state, PYPI + "/pypi/" + _path(ident) + "/" + _path(version) + "/json")
    doc = _json(reply)
    checks = out["checks"]
    info = doc.get("info") if isinstance(doc, dict) else None
    if not isinstance(info, dict):
        _check(
            checks,
            "published",
            False,
            "PyPI answered HTTP " + str(reply.status) + " for " + ident + " " + version,
        )
        return
    _check(checks, "published", True, ident + " " + str(info.get("version")) + " is on PyPI")
    found, glued = mcp_name_token(info.get("description"), name)
    if found:
        _check(checks, "mcp-name", True, "the README carries mcp-name: " + name)
    elif glued is not None:
        _check(
            checks,
            "mcp-name",
            False,
            "the README has mcp-name: "
            + name
            + " glued to "
            + json.dumps(glued)
            + ", not followed by a boundary",
        )
    else:
        others = sorted(
            set(re.findall(r"mcp-name: ([A-Za-z0-9._/-]+)", info.get("description") or ""))
        )
        _check(
            checks,
            "mcp-name",
            False,
            "the README has no mcp-name: "
            + name
            + ("; it names " + ", ".join(others[:3]) if others else ""),
        )
    if info.get("yanked"):
        out["warnings"].append(
            "yanked on PyPI: " + str(info.get("yanked_reason") or "no reason given")[:200]
        )
    urls = info.get("project_urls") or {}
    repo = None
    for key in ("Repository", "Source", "Source Code", "Code", "GitHub", "Homepage"):
        for label, value in urls.items():
            if label.lower() == key.lower() and _github_repo(value):
                repo = repo or value
    _repo_check(out, repo, owner, "project_urls")


def _nuget(state, package, name, owner, out):
    """The registry's NuGet check: the README at the flat container's ReadmeUriTemplate (the
    service index names api.nuget.org/v3-flatcontainer/), lower-cased id and version, SemVer build
    metadata dropped."""
    lower_id = out["identifier"].lower()
    lower_version = out["version"].lower().split("+", 1)[0]
    checks = out["checks"]
    reply = _get(
        state, NUGET_FLAT + _path(lower_id) + "/" + _path(lower_version) + "/readme", "text/plain"
    )
    if reply.status == 200:
        _check(
            checks,
            "published",
            True,
            out["identifier"] + " " + out["version"] + " has an embedded README on nuget.org",
        )
        found, glued = mcp_name_token(reply.text, name)
        if found:
            _check(checks, "mcp-name", True, "the README carries mcp-name: " + name)
        elif glued is not None:
            _check(
                checks,
                "mcp-name",
                False,
                "the README has mcp-name: "
                + name
                + " glued to "
                + json.dumps(glued)
                + ", not followed by a boundary",
            )
        else:
            _check(checks, "mcp-name", False, "the README has no mcp-name: " + name)
        return
    if reply.status != 404:
        _check(
            checks,
            "published",
            False,
            "nuget.org answered HTTP " + str(reply.status) + " for the README",
        )
        return
    index = _json(_get(state, NUGET_FLAT + _path(lower_id) + "/index.json"))
    versions = index.get("versions") if isinstance(index, dict) else None
    if not isinstance(versions, list):
        _check(checks, "published", False, out["identifier"] + " is not on nuget.org")
    elif lower_version not in [str(v).lower() for v in versions]:
        _check(
            checks,
            "published",
            False,
            out["identifier"] + " " + out["version"] + " is not on nuget.org",
        )
    else:
        _check(
            checks, "published", True, out["identifier"] + " " + out["version"] + " is on nuget.org"
        )
        _check(
            checks,
            "mcp-name",
            False,
            "the version has no embedded README, so it carries no mcp-name",
        )


def _dns(state, domain):
    reply = _get(state, DNS + "?name=" + domain + "&type=TXT", "application/dns-json")
    body = _json(reply)
    if not isinstance(body, dict) or "Status" not in body:
        return {
            "domain": domain,
            "ok": False,
            "problem": "dns.google answered HTTP " + str(reply.status),
        }
    keys = []
    for row in body.get("Answer") or []:
        if isinstance(row, dict) and row.get("type") == 16:
            keys.extend(proof_keys(_txt(row.get("data"))))
    return {"domain": domain, "ok": True, "dnssec_validated": body.get("AD") is True, "keys": keys}


def _domain_of(namespace):
    labels = namespace.lower().split(".")
    if labels[:2] == ["io", "github"]:
        return None, labels[2] if len(labels) == 3 else None
    return ".".join(reversed(labels)), None


def _host(value):
    text = str(value or "").strip().lower()
    if "://" in text:
        text = text.split("://", 1)[1]
    return text.split("/", 1)[0].rstrip(".")


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: name, optionally version and domain")
    name = str(payload.get("name") or "").strip()
    match = NAME.match(name)
    if not match or len(name) > 200:
        raise ValueError(
            "name must be a registry server name such as io.github.owner/server "
            "or com.example/server"
        )
    version = str(payload.get("version") or "latest").strip()
    if not version or len(version) > 255 or "/" in version:
        raise ValueError("version must be a version string, or latest")
    domain, github = _domain_of(match.group(1))
    if domain is None and github is None:
        raise ValueError("an io.github namespace is io.github.<owner>/<server>")
    asked = _host(payload.get("domain")) if payload.get("domain") else None
    if asked and asked != domain:
        raise ValueError(
            "domain must be the namespace's own domain (" + str(domain) + "): HTTP "
            "authentication covers the exact domain only"
        )

    state = {"fetches": 0}
    out = {"name": name, "asked_version": version}
    reply = _get(state, REGISTRY + "/v0.1/servers/" + _path(name) + "/versions/" + _path(version))
    entry = _json(reply)
    if not isinstance(entry, dict) or not isinstance(entry.get("server"), dict):
        out.update(
            found=False,
            verdict="not_found",
            fetches=state["fetches"],
            detail="the official registry answered HTTP " + str(reply.status),
        )
        return out
    server = entry["server"]
    official = (entry.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}
    out.update(
        found=True,
        version=server.get("version"),
        registry={
            k: official[k]
            for k in ("status", "isLatest", "publishedAt", "updatedAt")
            if k in official
        },
    )
    problems, unchecked, warnings = [], [], []
    if official.get("status") not in (None, "active"):
        warnings.append("the registry marks this version " + str(official["status"]))

    namespace = (
        {"kind": "github", "owner": github} if github else {"kind": "domain", "domain": domain}
    )
    out["namespace"] = namespace
    if github:
        repo_url = (server.get("repository") or {}).get("url")
        got = _github_repo(repo_url)
        namespace["repository"] = repo_url
        namespace["repository_owner_matches"] = None if got is None else got[0] == github
        if got is not None and got[0] != github:
            warnings.append("server.json repository " + str(repo_url) + " is not under " + github)

    packages = []
    for package in (server.get("packages") or [])[:8]:
        if not isinstance(package, dict):
            continue
        kind = str(package.get("registryType") or "")
        item = {
            "registry_type": kind,
            "identifier": str(package.get("identifier") or ""),
            "version": str(package.get("version") or ""),
        }
        packages.append(item)
        base = {"npm": NPM, "pypi": PYPI, "nuget": NUGET}.get(kind)
        if base is None:
            item.update(checked=False, reason=NOT_CHECKED.get(kind, "unknown registry type"))
        elif str(package.get("registryBaseUrl") or base).rstrip("/") != base:
            item.update(checked=False, reason="registryBaseUrl is not " + base)
        elif not item["identifier"] or not item["version"]:
            item.update(checked=True, checks=[])
            _check(item["checks"], "published", False, "server.json gives no identifier or version")
        else:
            item.update(checked=True, checks=[], warnings=[])
            try:
                {"npm": _npm, "pypi": _pypi, "nuget": _nuget}[kind](
                    state, package, name, github, item
                )
            except _Budget:
                item.update(checked=False, reason="the call's six requests were used up")
                item.pop("checks", None)
            except Exception as exc:  # the hearth refused the request; never the fetch signal
                item.update(checked=False, reason="request failed: " + str(exc)[:160])
                item.pop("checks", None)
        for check in item.get("checks") or []:
            if check["ok"] is False:
                problems.append(kind + " " + item["identifier"] + ": " + check["detail"])
        warnings.extend(
            kind + " " + item["identifier"] + ": " + w for w in item.get("warnings") or []
        )
        if not item.get("checked"):
            unchecked.append(kind + " " + item["identifier"] + ": " + item["reason"])
    out["packages"] = packages

    remotes = []
    for remote in (server.get("remotes") or [])[:8]:
        if isinstance(remote, dict):
            row = {
                "type": remote.get("type"),
                "url": remote.get("url"),
                "templated": "{" in str(remote.get("url")),
            }
            if domain:
                host = _host(remote.get("url")).split(":", 1)[0]
                row["on_namespace_domain"] = host == domain or host.endswith("." + domain)
            remotes.append(row)
    out["remotes"] = remotes

    if domain:
        candidates = [domain]
        if domain.count(".") >= 2:
            candidates.append(domain.split(".", 1)[1])
        lookups = []
        try:
            for candidate in candidates:
                seen = _dns(state, candidate)
                lookups.append(seen)
                if any(key["valid"] for key in seen.get("keys") or []):
                    break
        except _Budget:
            unchecked.append("DNS: the call's six requests were used up")
        except Exception as exc:
            unchecked.append("DNS: request failed: " + str(exc)[:160])
        namespace["dns"] = lookups
        dns_ok = any(key["valid"] for seen in lookups for key in seen.get("keys") or [])
        http_ok = None
        if asked:
            url = "https://" + asked + "/.well-known/mcp-registry-auth"
            try:
                reply = _get(state, url, "text/plain")
                keys = proof_keys(reply.text) if reply.ok else []
                http = {"url": url, "status": reply.status, "keys": keys}
                if 300 <= reply.status < 400:
                    http["note"] = "a redirect: the registry does not follow it either"
                elif reply.ok and not keys:
                    http["note"] = "answers 200 but holds no MCPv1 record"
                if asked == "github.io" or asked.endswith(".github.io"):
                    http["note"] = "the registry refuses HTTP authentication for github.io domains"
                    keys = []
                http_ok = any(key["valid"] for key in keys)
                namespace["http"] = http
            except _Budget:
                unchecked.append("HTTP: the call's six requests were used up")
            except Exception as exc:
                unchecked.append("HTTP: request failed: " + str(exc)[:160])
        namespace["publishes_registry_key"] = dns_ok or bool(http_ok)
        if lookups and all(seen["ok"] for seen in lookups) and not dns_ok:
            where = " or ".join(seen["domain"] for seen in lookups)
            if http_ok is False:
                problems.append(
                    "no valid MCPv1 key in DNS at "
                    + where
                    + " nor at "
                    + namespace["http"]["url"]
                    + ": the domain does not authorize registry publishing now"
                )
            elif http_ok is None:
                unchecked.append(
                    "no valid MCPv1 key in DNS at " + where + "; the publisher may use "
                    "HTTP authentication: give domain to read /.well-known/mcp-registry-auth"
                )

    out["problems"] = problems
    out["warnings"] = warnings
    out["not_checked"] = unchecked
    if problems:
        out["verdict"] = "mismatch"
    elif unchecked or (not packages and github):
        out["verdict"] = "verified_partly"
    else:
        out["verdict"] = "verified"
    out["fetches"] = state["fetches"]
    return out
