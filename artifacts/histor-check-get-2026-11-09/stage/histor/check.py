"""/check — "is what I just received what everyone else is seeing?"

A client about to trust an MCP server already holds the thing MTL/1 section 4.6 says is
expensive to get: the tool set, retrieved by itself, from the server. So the check needs no
execution on our side. The client sends the endpoint and either the tools or their MTL/1
digest; HISTOR answers, signed, with what it has observed at that endpoint.

Clients that opt in (``contribute: true``) add their digest to a per-day count. That count is
what makes a server that shows different clients different definitions visible at all: a
crawler sees one view, a local scanner sees one view, only a comparison across many sees the
split. Nothing but ``(target, digest, day)`` is stored — no address, no account, no tools.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from awr import SigningKey

from histor.declared import public as declared_public
from histor.logbook import sign_document, utcnow
from histor.lookalike import default_index
from histor.mcpclient import MAX_TOOLS
from histor.packages import package_key
from histor.scanner import Scanner, ScannerError
from histor.store import Store, dumps
from histor.subject import MtlError, tool_set_digest

CHECK_TYPE = "histor.check/v1"
SRI = re.compile(r"^sha256-[A-Za-z0-9+/]{43}=$")
MAX_MATCHES = 200          # matches returned per answer; the per-tier counts cover all of them
CHECK_SCAN_TIMEOUT_S = 30  # a /check scan is one set, not a crawl batch
# One fresh scan at a time for the whole site: a scan is a Node subprocess, and callers queueing
# behind each other is exactly the stall this prevents. A caller who finds it busy is told so.
_SCAN_SLOT = threading.Semaphore(1)

# What may be counted as an unlisted host: a public DNS name. Never an address literal or a name that
# only means something inside one network — those say where a person works, not what to watch.
_HOSTNAME = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$")
_LOCAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet", ".private",
                   ".test", ".example", ".invalid", ".localdomain", ".home.arpa")


def unlisted_host(endpoint: str) -> str | None:
    """The host of an https endpoint, if it is a public DNS name; the path and query are dropped."""
    try:
        parts = urlsplit(endpoint.strip())
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if parts.scheme != "https" or not _HOSTNAME.match(host) or host.endswith(_LOCAL_SUFFIXES):
        return None
    return host

NOTES = {
    "not-listed": (
        "HISTOR has no record of this endpoint or name in the registries it reads. It counts the host name of an "
        "endpoint it does not know (host and day, nothing else) to decide which servers to watch next."
    ),
    "not-observed": "HISTOR lists this endpoint but has not retrieved its tool definitions (see lastStatus).",
    "same": "The tool definitions you sent are the set HISTOR currently observes at this endpoint.",
    "previously-observed": (
        "The tool definitions you sent match a set HISTOR observed at this endpoint earlier, not the current one."
    ),
    "different": (
        "The tool definitions you sent differ from every set HISTOR has observed at this endpoint. Possible causes: "
        "the server changed after HISTOR's last observation, its definitions vary per account, or it shows different "
        "clients different definitions. Read the definitions again before approving them."
    ),
    "no-digest": "No tool set was sent, so only HISTOR's own observations are reported.",
    # A package runs on the client's machine, not at one endpoint: what it lists can depend on what that
    # machine has. A launcher hands stdio to a locally installed program and offers only an "install me"
    # tool where the program is missing, as it is in HISTOR's sandbox.
    "different-package": (
        "The tool definitions you sent differ from every set HISTOR has observed from this package, in any version "
        "it ran. Possible causes: the package lists tools according to what your machine has and HISTOR's sandbox "
        "has not (a program it hands over to, a real key or setting), you run a version HISTOR has not reached yet, "
        "or the package you run is not the one published. Read the definitions again before approving them."
    ),
    "undigestible": (
        "The tools you sent are not digestible under MTL/1 (see query.digestError), so they cannot be compared "
        "with HISTOR's record. HISTOR's own observations are reported."
    ),
}
MAX_CLASSIFIER_FINDINGS = 50
NOTE_CLASSIFIER = (
    "One model's advisory opinion, read over the tool text in any language. It is not a log label and is "
    "not reproducible: this signature attests only that HISTOR holds this verdict for this tool set, not "
    "that the verdict is right. Treat it as a lead to check, not proof. Coverage: if checkedTools is below "
    "toolCount, only the first checkedTools tools were examined; truncatedTools counts tools with a field "
    "longer than the model was shown, of which it read the start and the end."
)
NOTE_CLASSIFIER_NONE = (
    "HISTOR holds no classifier verdict for this tool set. The classifier runs during HISTOR's daily crawl, "
    "over sets HISTOR observed itself; /check reads stored verdicts and never calls a model."
)
NOTE_DECLARED = (
    " The publisher declares this set {where}{when}. That is the publisher's word, not an observation: HISTOR "
    "has not seen this set served."
)
NOTE_DELISTED = " This endpoint is no longer listed in the registry; HISTOR's record stops at {day}."
# lastStatus robots-disallowed / robots-unreachable (histor.robots): HISTOR leaves the server alone.
NOTE_ROBOTS_SINCE = (
    " HISTOR does not read this endpoint: its site's robots.txt does not allow HISTOR (RFC 9309). Changes to its "
    "tools after {day} are not recorded; the comparison is with its last observation."
)
NOTE_ROBOTS_NEVER = (
    " HISTOR does not read this endpoint: its site's robots.txt does not allow HISTOR (RFC 9309), so HISTOR has "
    "no independent record of its tools."
)
# lastStatus pay-per-crawl (histor.mcpclient): the site charges crawlers for each read; HISTOR does not pay.
NOTE_PAYCRAWL_SINCE = (
    " HISTOR does not read this endpoint: its site charges crawlers for each read, and HISTOR does not pay for "
    "reads. Changes to its tools after {day} are not recorded; the comparison is with its last observation."
)
NOTE_PAYCRAWL_NEVER = (
    " HISTOR does not read this endpoint: its site charges crawlers for each read, and HISTOR does not pay for "
    "reads, so HISTOR has no independent record of its tools."
)
NOTE_LAST_FAILED = (
    " HISTOR's latest attempt at this endpoint produced no tool set ({status}); the comparison is with its "
    "last successful observation."
)


class CheckError(ValueError):
    pass


MISSING_SUBJECT = (
    "send endpoint, package or name, for example "
    'POST {"endpoint": "https://example.com/mcp", "tools": [...]} or '
    "GET /api/v1/check?endpoint=https://example.com/mcp"
)


class Checker:
    def __init__(self, store: Store, key: SigningKey, scanner: Scanner, public_base: str,
                 *, classifier_model: str = "", classifier_enabled: bool = False) -> None:
        self.store = store
        self.key = key
        self.scanner = scanner
        self.public_base = public_base
        self.classifier_model = classifier_model
        self.classifier_enabled = classifier_enabled

    def check(self, body: dict[str, Any], *, allow_scan: bool | Callable[[], bool],
              may_contribute: Callable[[str], bool] | None = None,
              may_count_unlisted: Callable[[str], bool] | None = None) -> dict[str, Any]:
        """*allow_scan* may be a callable: it is asked only when a fresh scan is about to run, so a
        check that needs none does not spend the caller's scan budget."""
        # "url" is what outside callers send most often when they guess the field (2026-11 logs);
        # it means the endpoint, so it is read as one instead of being refused.
        endpoint_field = "endpoint" if body.get("endpoint") is not None else "url"
        endpoint = body.get(endpoint_field)
        name = body.get("name")
        package = body.get("package")
        for field, value in ((endpoint_field, endpoint), ("name", name), ("package", package)):
            if value is not None and (not isinstance(value, str) or "\x00" in value or len(value) > 2000):
                raise CheckError(f"{field} must be a string of at most 2000 characters")
        if package:
            # A stdio server: "npm:<name>" or "pypi:<name>", as the client launched it. PyPI names
            # are compared normalised (PEP 503), so the client need not normalise them itself.
            registry, _, pkg_name = package.partition(":")
            key = package_key(registry, pkg_name)
            if key is None:
                raise CheckError("package must be npm:<name> or pypi:<name>")
            endpoint = key
        if not endpoint and not name:
            raise CheckError(f"{MISSING_SUBJECT} (the form: {self.public_base}/check)")

        client_digest: str | None = None
        client_entries: list[dict[str, Any]] | None = None
        digest_error: dict[str, str] | None = None
        if body.get("tools") is not None:
            if not isinstance(body["tools"], list):
                raise CheckError("tools must be the tools array of a tools/list result")
            if len(body["tools"]) > MAX_TOOLS:
                raise CheckError(f"more than {MAX_TOOLS} tools")
            try:
                client_digest, client_entries = tool_set_digest(body["tools"])
            except MtlError as exc:
                digest_error = {"code": exc.code, "detail": exc.detail}
        elif body.get("toolSetDigest") is not None:
            if not isinstance(body["toolSetDigest"], str) or not SRI.match(body["toolSetDigest"]):
                raise CheckError("toolSetDigest must be an MTL/1 tool-set digest (sha256-<base64>)")
            client_digest = body["toolSetDigest"]

        candidates = self.store.targets_by(endpoint=endpoint) if endpoint else self.store.targets_by(name=name)
        target = next((t for t in candidates if not t["delisted"]), candidates[0] if candidates else None)

        result: dict[str, Any] = {
            "type": CHECK_TYPE,
            "checkedAt": utcnow(),
            "issuer": self.key.did,
            "query": {k: v for k, v in (("package" if package else "endpoint", endpoint), ("name", name),
                                        ("toolSetDigest", client_digest)) if v},
        }
        if digest_error:
            result["query"]["digestError"] = digest_error

        if target is None:
            state = "not-listed"
            host = unlisted_host(endpoint) if endpoint and not package else None
            if host and (may_count_unlisted is None or may_count_unlisted(host)):
                self.store.add_unlisted_query(host, datetime.now(UTC).strftime("%Y-%m-%d"))
        else:
            result["target"] = {
                "id": target["id"],
                "name": target["name"],
                "endpoint": target["endpoint"],
                "page": f"{self.public_base}/s/{target['id']}",
                "badge": f"{self.public_base}/badge/{target['id']}.svg",
                "lastStatus": target["last_status"],
                "listed": not target["delisted"],
            }
            if target.get("package_version"):
                result["target"]["packageVersion"] = target["package_version"]
            card = self.store.server_card(target["id"])
            if card and card.get("status") == "declared":
                # The operator's server card (histor.cards): what it declares, not what HISTOR observed.
                result["target"]["serverCard"] = {k: card[k] for k in ("url", "toolSetDigest", "toolCount", "checkedAt") if k in card}
            if target.get("package_signals"):
                try:
                    result["target"]["packageSignals"] = json.loads(target["package_signals"])
                except ValueError:
                    pass
            if target["current_toolset"] or target["current_subject"]:
                result["observed"] = {
                    k: v for k, v in (
                        ("toolSetDigest", target["current_toolset"]),
                        ("subjectDigest", target["current_subject"]),
                        ("toolCount", target["current_count"]),
                        ("firstPinned", target["first_pinned"]),
                        ("unchangedSince", target["unchanged_since"]),
                        ("lastObserved", target["last_ok"]),
                        ("observations", target["ok_observations"]),
                        ("changes", target["changes"]),
                    ) if v is not None
                }
            if not target["current_subject"]:
                state = "not-observed"
            elif digest_error:
                state = "undigestible"
            elif client_digest is None:
                state = "no-digest"
            elif target["current_toolset"] and client_digest == target["current_toolset"]:
                state = "same"
            else:
                seen = self.store.toolset_seen(target["id"], client_digest)
                if seen:
                    state = "previously-observed"
                    result["seenBefore"] = seen
                else:
                    state = "different"
            if client_digest and state != "same":
                # The publisher's own account of a set HISTOR did not observe, e.g. a launcher's tools
                # on a machine where its program is installed (histor.declared).
                row = self.store.declared_toolset(target["id"], client_digest)
                if row:
                    result["declared"] = declared_public(row)
            if (body.get("contribute") is True and client_digest
                    and (may_contribute is None or may_contribute(target["id"]))):
                day = datetime.now(UTC).strftime("%Y-%m-%d")
                self.store.add_client_report(target["id"], client_digest, day)
                result["contributed"] = True

        result["match"] = state
        if package:
            # A name made to be taken for a popular one — asked for any package, listed or not:
            # a typosquat is usually published the day it is used.
            try:
                lookalike = default_index().check(endpoint)
            except (OSError, ValueError):
                lookalike = None
            if lookalike:
                result["packageLookalike"] = lookalike
        note = NOTES["different-package" if package and state == "different" else state]
        if result.get("declared") and state in ("different", "not-observed"):
            declared = result["declared"]
            where = (f"in the declaration file its registry entry points at ({declared['url']})"
                     if declared.get("source") == "url" and declared.get("url")
                     else f"in its server card ({declared['url']})" if declared.get("source") == "card" and declared.get("url")
                     else "in its registry entry")
            note += NOTE_DECLARED.format(where=where, when=f' ("{declared["when"]}")' if declared.get("when") else "")
        last_status = str(target["last_status"] or "") if target is not None else ""
        left_alone = ((NOTE_ROBOTS_NEVER, NOTE_ROBOTS_SINCE) if last_status.startswith("robots-")
                      else (NOTE_PAYCRAWL_NEVER, NOTE_PAYCRAWL_SINCE) if last_status == "pay-per-crawl" else None)
        if left_alone and state == "not-observed":
            note += left_alone[0]
        if target is not None and state not in ("not-listed", "not-observed"):
            if target["delisted"]:
                note += NOTE_DELISTED.format(day=str(target["last_listed"] or "")[:10])
            if left_alone:
                note += left_alone[1].format(day=str(target["last_ok"] or "")[:10])
            elif target["last_status"] and target["last_status"] != "ok":
                note += NOTE_LAST_FAILED.format(status=target["last_status"])
        result["note"] = note
        scan = self._scan(client_digest, client_entries, target, digest_error is not None, allow_scan)
        if scan is not None:
            result["patternScan"] = scan
        classifier = self._classifier(client_digest, target, digest_error is not None)
        if classifier is not None:
            result["classifier"] = classifier
        sth = self.store.latest_sth()
        if sth:
            result["log"] = {"treeSize": sth["treeSize"], "rootHash": sth["rootHash"], "timestamp": sth["timestamp"]}
        return sign_document(self.key, result)

    def _classifier(self, client_digest: str | None, target: dict[str, Any] | None,
                    sent_undigestible: bool) -> dict[str, Any] | None:
        """The stored advisory classifier verdict for the set the client holds, or a statement that
        there is none.

        Same honesty rules as the pattern scan: never another set's verdict presented as theirs (an
        undigestible set gets nothing), and never a model call here — /check is public and rate
        limited per address, and a paid call per anonymous request would be a way to spend HISTOR's
        money. Only verdicts the crawl already stored are reported.
        """
        if sent_undigestible:
            return None
        digest = client_digest or (target or {}).get("current_toolset")
        if not digest:
            return None
        # The model the crawl runs now, like the server page; with the classifier off, whatever a
        # model judged before is still a fact HISTOR holds, so the newest stored verdict is used.
        if self.classifier_model:
            verdict = self.store.classification(digest, self.classifier_model)
        else:
            verdict = self.store.latest_classification(digest)
        if verdict is None:
            if not self.classifier_enabled:
                return None  # no classifier on this instance: say nothing rather than promise one
            return {"status": "not-classified", "toolSetDigest": digest, "advisory": True, "note": NOTE_CLASSIFIER_NONE}
        findings = [f for f in verdict.get("findings", []) if isinstance(f, dict)]
        return {
            "status": "classified",
            "toolSetDigest": digest,
            "model": verdict.get("model"),
            "classifiedAt": verdict.get("updatedAt"),
            "checkedTools": verdict.get("checkedTools"),
            "toolCount": verdict.get("toolCount"),
            "truncatedTools": verdict.get("truncatedTools"),
            "flagged": len(findings),
            # Names are stored with each finding at classification time: no multi-megabyte tool set
            # is loaded per /check request just to say which tool was flagged.
            "findings": findings[:MAX_CLASSIFIER_FINDINGS],
            "truncated": len(findings) > MAX_CLASSIFIER_FINDINGS,
            "advisory": True,
            "note": NOTE_CLASSIFIER,
        }

    def _pattern_set(self) -> str | None:
        """The pattern set a fresh scan would use now: the running sidecar's, not the last crawl's."""
        try:
            return self.scanner.rulesets().pattern_set_digest
        except ScannerError:
            return self.store.get_meta("pattern_set")

    def _scan(self, client_digest: str | None, entries: list[dict[str, Any]] | None, target: dict[str, Any] | None,
              sent_undigestible: bool, allow_scan: bool | Callable[[], bool]) -> dict[str, Any] | None:
        """WARDEN pattern matches for the set the client holds — cached, or computed if allowed.

        Never a scan of some OTHER set: when the client sent tools HISTOR cannot digest, there is
        nothing to report rather than the observed set's matches presented as theirs.
        """
        if sent_undigestible:
            return None
        pattern_set = self._pattern_set()
        digest = client_digest or (target or {}).get("current_toolset")
        if not digest or not pattern_set:
            return None
        with self.store.db.read() as tx:
            row = tx.one("SELECT matches FROM scans WHERE toolset=? AND pattern_set=?", (digest, pattern_set))
        if row is not None:
            matches = json.loads(row["matches"])
        elif entries is not None and (allow_scan() if callable(allow_scan) else allow_scan):
            if not _SCAN_SLOT.acquire(blocking=False):
                return {"status": "busy", "note": "Another scan is running; try again in a moment."}
            try:
                out = self.scanner.scan([{"id": "check", "server": {"id": (target or {}).get("name", "")},
                                          "tools": entries}], timeout=CHECK_SCAN_TIMEOUT_S)
            except ScannerError:
                return {"status": "unavailable"}
            finally:
                _SCAN_SLOT.release()
            matches = out["check"]["patternMatches"]
            if self.store.has_blob(digest, "toolset"):
                # Cached only for sets HISTOR itself observed: a stranger's set is scanned for them
                # and forgotten, so anonymous callers cannot grow the table (audit F13).
                with self.store.db.transaction() as tx:
                    tx.execute(
                        "INSERT INTO scans(toolset, pattern_set, matches) VALUES(?, ?, ?) "
                        "ON CONFLICT(toolset, pattern_set) DO NOTHING",
                        (digest, pattern_set, dumps(matches)),
                    )
        else:
            return {"status": "not-scanned"}
        return {
            "status": "scanned",
            "toolSetDigest": digest,
            "patternSet": pattern_set,
            "block": sum(1 for m in matches if m["tier"] == "block"),
            "advise": sum(1 for m in matches if m["tier"] == "advise"),
            "matches": matches[:MAX_MATCHES],
            **({"truncated": len(matches)} if len(matches) > MAX_MATCHES else {}),
            "note": "A match is a reason to read the definition, not a finding of fact. Advise-tier matches never block in WARDEN.",
        }
