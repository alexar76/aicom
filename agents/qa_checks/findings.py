"""Findings QA trusts or drops: insecure auth, acceptance traceability, and findings the tree
itself contradicts.
"""

from __future__ import annotations

import re
from pathlib import Path

from .tree import TreeReadingMixin


class FindingsMixin:
    """Insecure auth, acceptance traceability, and dropping findings the tree contradicts."""

    def _scan_for_insecure_auth(self, code_files: list[dict]) -> list[dict]:
        """Detect trivial hard-coded auth patterns (e.g. demo login stubs)."""
        issues: list[dict] = []
        for file_info in code_files:
            path = file_info.get("path", "")
            content = file_info.get("content", "")
            lower = content.lower()
            if "login" not in lower and "auth" not in lower:
                continue
            # Very basic heuristic: hard-coded email/password pair in a conditional.
            if "admin@example.com" in lower and "password" in lower and "== 'password'" in content:
                issues.append(
                    {
                        "severity": "high",
                        "issue": "Hard-coded demo credentials in authentication logic",
                        "affected_code": path,
                        "recommendation": (
                            "Remove hard-coded email/password checks. Introduce a user store and "
                            "verify hashed passwords instead."
                        ),
                    }
                )
        return issues

    def _assess_acceptance_traceability(self, spec_payload: dict, code_files: list[dict]) -> dict:
        """
        Check that generated tests reference acceptance criteria semantics.
        Lightweight heuristic for now: keyword overlap from criteria -> test files.
        """
        inner = spec_payload.get("specification") if isinstance(spec_payload, dict) and "specification" in spec_payload else spec_payload
        spec = inner if isinstance(inner, dict) else {}

        criteria: list[str] = []
        for us in spec.get("user_stories") or []:
            if isinstance(us, dict):
                ac = us.get("acceptance_criteria")
                if isinstance(ac, str) and ac.strip():
                    criteria.append(ac.strip())
        for fr in spec.get("functional_requirements") or []:
            if isinstance(fr, dict):
                ac = fr.get("acceptance_criteria")
                if isinstance(ac, str) and ac.strip():
                    criteria.append(ac.strip())

        if not criteria:
            return {"passed": True, "criteria_total": 0, "covered": 0, "summary": "No acceptance criteria to trace."}

        test_files = [
            f for f in code_files
            if Path(str(f.get("path", ""))).name.startswith("test_")
            or "/tests/" in str(f.get("path", "")).replace("\\", "/").lower()
        ]
        if not test_files:
            return {
                "passed": False,
                "criteria_total": len(criteria),
                "covered": 0,
                "summary": "Specification has acceptance criteria but no explicit test files were generated.",
            }

        test_blob = "\n".join(str(f.get("content", "")).lower() for f in test_files)

        stop = {"with", "from", "that", "this", "have", "will", "must", "should", "when", "then", "user", "users", "into", "over", "under", "after", "before", "their", "there", "where"}
        covered = 0
        missing_samples: list[str] = []
        for c in criteria:
            tokens = [t for t in re.split(r"[^a-z0-9]+", c.lower()) if len(t) >= 5 and t not in stop]
            key_tokens = tokens[:5]
            if key_tokens and any(tok in test_blob for tok in key_tokens):
                covered += 1
            else:
                missing_samples.append(c[:120])

        ratio = covered / max(1, len(criteria))
        passed = ratio >= 0.5
        return {
            "passed": passed,
            "criteria_total": len(criteria),
            "covered": covered,
            "coverage_ratio": round(ratio, 3),
            "missing_examples": missing_samples[:5],
            "summary": (
                f"Acceptance criteria coverage in tests: {covered}/{len(criteria)} "
                f"({int(ratio * 100)}%). Minimum required: 50%."
            ),
        }

    @staticmethod
    def _drop_findings_the_tree_contradicts(
        bugs: list[dict], code_root: Path, *, log
    ) -> list[dict]:
        """Remove findings that claim a file is missing when the file is on disk.

        Measured live on a product at four remaining defects: an LLM finding read "No README.md,
        LICENSE, CHANGELOG.md, docs/, docs/badges/, .github/workflows/ci.yml, or
        .github/workflows/release.yml were provided. These are mandatory for full_software
        products." All seven were in the tree. A round cannot create a file that already exists, so
        the finding was immortal — and it held a blocking gate red while every round that tried to
        satisfy it wrote files that were already there.

        Only claims OF ABSENCE are filtered, and only when every path named exists. A finding that
        names three files of which one is genuinely missing keeps its place, narrowed to the file
        that is actually missing, because that part of it is true.
        """
        import re as _re

        absence = _re.compile(
            r"\b(no|missing|absent|not provided|were not provided|does not exist|not found|"
            r"lacks|without)\b",
            _re.I,
        )
        path_like = _re.compile(
            r"[\w./-]*[\w-]+\.(?:md|yml|yaml|json|py|ts|tsx|txt|toml|cfg)\b"
            r"|(?:docs|tests|\.github)(?:/[\w.-]+)*/?"
            # Extension-less files a contract names by convention. LICENSE was the one the live
            # phantom hinged on: without it the claim looked partly true and survived.
            r"|\b(?:LICEN[SC]E|NOTICE|CODEOWNERS|CONTRIBUTING|Dockerfile|Makefile)\b"
        )
        # Only LLM guesses are filtered. A finding produced by a detector that READ the tree cannot
        # be contradicted by the tree — it is the tree's own report. This bit was learned the hard
        # way, one round after the filter shipped: `orm_schema_never_created` says "migrations exist
        # (…0001_initial.py) but nothing runs alembic upgrade", which mentions files that do exist,
        # and the filter dropped the one finding that had correctly diagnosed a database with no
        # schema. Two fixes, each right on its own, cancelling each other out.
        measured_prefixes = (
            "Module health:",
            "API contract:",
            "Browser E2E:",
            "Demo journey:",
            "Demo/TZ gate:",
            "Frontend build:",
            "Backend runtime:",
        )
        truncated = _re.compile(
            r"\b(truncated|cut off|appears truncated|incomplete (?:rate_limit )?decorator)\b",
            _re.I,
        )
        kept: list[dict] = []
        for bug in bugs:
            title = str(bug.get("title") or "")
            if title.startswith(measured_prefixes):
                kept.append(bug)
                continue
            blob = f"{title} {bug.get('description') or ''} {bug.get('file') or ''}"
            # LLM saw a truncated ATTACHMENT and reported the file as incomplete. Measured
            # on Sentinel round 50: "rate_limit decorator is truncated after @wraps" and
            # "app/main.py appears truncated" while both files parsed. Those two "critical"
            # findings then competed with the real compile and 401 defects for attention.
            if truncated.search(blob):
                named_py = [
                    str(bug.get("file") or "").strip().lstrip("/")
                ] + path_like.findall(blob)
                named_py = [
                    r.strip().rstrip(",;:").lstrip("/")
                    for r in named_py
                    if str(r).endswith(".py")
                ]
                if named_py and all(
                    TreeReadingMixin._py_file_parses(code_root, rel) for rel in named_py if rel
                ):
                    log(
                        "INFO",
                        "Dropping a truncated-file finding the tree contradicts: "
                        f"{', '.join(named_py[:4])} parse — {title[:80]}",
                    )
                    continue
            # LLM saw the first 10 attached files and declared the repo "incomplete / missing
            # modules" while backend/ and frontend/ were on disk. app/main.py in the finding is
            # the truncated path of backend/app/main.py, so the absence filter kept it (that
            # exact relpath does not exist) and it competed with contrast for the round.
            if _re.search(
                r"repository is incomplete|incomplete\s*/\s*missing modules|missing modules",
                title,
                _re.I,
            ) and (
                (code_root / "backend").is_dir()
                and (
                    (code_root / "frontend").is_dir()
                    or (code_root / "index.html").is_file()
                )
            ):
                log(
                    "INFO",
                    "Dropping an incomplete-repo finding the tree contradicts: "
                    f"backend+frontend are present — {title[:80]}",
                )
                continue
            if not absence.search(blob):
                kept.append(bug)
                continue
            named = []
            for raw in path_like.findall(blob):
                # Trailing punctuation only. A two-sided strip ate the leading dot of
                # ".github/workflows/ci.yml", turning an existing path into a missing one — which
                # made the phantom look partly true and let it survive the filter.
                rel = str(raw).strip().rstrip(",;:").lstrip("/")
                if rel.endswith(".") and not rel.endswith(".."):
                    rel = rel[:-1]
                if rel and rel not in named:
                    named.append(rel)
            if not named:
                kept.append(bug)
                continue
            missing = [rel for rel in named if not (code_root / rel).exists()]
            if not missing:
                log(
                    "INFO",
                    "Dropping a finding the tree contradicts: it says "
                    f"{', '.join(named[:6])} are missing, and all of them exist — "
                    f"{str(bug.get('title'))[:80]}",
                )
                continue
            if len(missing) < len(named):
                bug = dict(bug)
                bug["description"] = (
                    f"{str(bug.get('description') or '')[:400]} "
                    f"[verified against the tree: only {', '.join(missing[:6])} "
                    f"{'is' if len(missing) == 1 else 'are'} actually missing; the rest exist]"
                )
            kept.append(bug)
        if any("auth_rejected" in str(b.get("title") or "") for b in kept):
            # The measured journey finding already says how this client authenticates.
            # An LLM restatement ("Authentication only reads cookie token") is the same
            # defect at medium, and it was what the round followed instead of deps.py.
            filtered = []
            for bug in kept:
                title = str(bug.get("title") or "")
                if title.startswith(measured_prefixes):
                    filtered.append(bug)
                    continue
                blob = f"{title} {bug.get('description') or ''}".lower()
                if "cookie" in blob and any(
                    w in blob for w in ("get_current_user", "bearer", "authorization")
                ):
                    log(
                        "INFO",
                        "Dropping LLM restatement of a measured auth_rejected finding: "
                        f"{title[:80]}",
                    )
                    continue
                filtered.append(bug)
            kept = filtered
        return kept
