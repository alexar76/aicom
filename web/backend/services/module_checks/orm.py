"""SQLAlchemy: mismatched back_populates, models nothing registers, tables never created,
duplicate table names.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

from .common import _canonical_home, MAX_FINDINGS


def find_mismatched_back_populates(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """A ``relationship(back_populates=…)`` whose other side does not exist.

    The SQLAlchemy twin of ``missing_attribute``, found the same way its siblings were — a live
    product dead at boot with every static counter at zero::

        sqlalchemy.exc.InvalidRequestError: Mapper 'Mapper[Advisory(advisories)]' has no property
        'invoke_logs'. If this property was indicated from other mappers …

    ``InvokeAuditLog`` pointed back at ``Advisory.invoke_logs`` while ``Advisory`` calls that field
    ``audit_logs``. The mapper configures lazily, so the first query kills the app; nothing importable
    is wrong, so every import-level detector stayed silent and the rounds went back to guessing —
    measured: two rounds editing ``deps.py`` while both halves of the defect sat in the models.

    Precision rules, since this reports critical: only classes this product defines, targets resolved
    by class name, and a target that cannot be found is missing_symbol territory rather than a
    mismatch. The finding names both files and both attribute names, because the fix is a one-token
    rename on whichever side is wrong.
    """
    # class name -> {"file": rel, "line": int, "rels": {attr: (target, back_populates)}}
    classes: dict[str, dict[str, Any]] = {}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        rel_path = file.relative_to(code_dir).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            attrs: dict[str, Any] = {}
            rels: dict[str, tuple[str, str | None, int]] = {}
            for stmt in node.body:
                targets = []
                value = None
                if isinstance(stmt, ast.Assign):
                    targets = [x.id for x in stmt.targets if isinstance(x, ast.Name)]
                    value = stmt.value
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    targets = [stmt.target.id]
                    value = stmt.value
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    attrs[stmt.name] = True
                    continue
                for name in targets:
                    attrs[name] = True
                if not targets or not isinstance(value, ast.Call):
                    continue
                func = value.func
                func_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if func_name != "relationship":
                    continue
                target_cls = ""
                if value.args:
                    a0 = value.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        target_cls = a0.value
                    elif isinstance(a0, ast.Name):
                        target_cls = a0.id
                back = None
                for kw in value.keywords:
                    if kw.arg == "back_populates" and isinstance(kw.value, ast.Constant):
                        back = kw.value.value
                if target_cls:
                    rels[targets[0]] = (target_cls, back, stmt.lineno)
            if attrs or rels:
                classes[node.name] = {
                    "file": rel_path,
                    "line": node.lineno,
                    "attrs": attrs,
                    "rels": rels,
                }

    import difflib

    findings: list[dict[str, Any]] = []
    for cls_name, info in sorted(classes.items()):
        for attr, (target_cls, back, lineno) in sorted(info["rels"].items()):
            if not back:
                continue
            target = classes.get(target_cls)
            if target is None:
                continue  # unknown class: missing_symbol territory, not a mismatch
            if back in target["attrs"] or back in target["rels"]:
                continue
            # The reciprocal attr the target actually has, if any: a relationship pointing back here.
            candidates = [
                a for a, (tc, _b, _l) in target["rels"].items() if tc == cls_name
            ] or difflib.get_close_matches(back, sorted(target["attrs"]), n=2, cutoff=0.6)
            findings.append(
                {
                    "code": "mismatched_back_populates",
                    "severity": "critical",
                    "file": info["file"],
                    "line": lineno,
                    "class": cls_name,
                    "attr": attr,
                    "target": target_cls,
                    "expected": back,
                    "did_you_mean": candidates[:2],
                    "detail": (
                        f"{info['file']}:{lineno}: {cls_name}.{attr} = relationship("
                        f"\"{target_cls}\", back_populates=\"{back}\") — but {target_cls} in "
                        f"{target['file']} has no attribute '{back}'. SQLAlchemy raises "
                        f"InvalidRequestError (\"Mapper has no property '{back}'\") when the mapper "
                        "first configures, so the app dies on its first query. "
                        + (
                            f"{target_cls} calls its side {' / '.join(repr(c) for c in candidates[:2])} — "
                            f"make the pair agree with a ONE-TOKEN rename on whichever side is wrong. "
                            if candidates
                            else f"Add the matching relationship to {target_cls} or fix the name. "
                        )
                        + "Do not delete the relationship: whatever queries it breaks next."
                    ),
                }
            )
            if len(findings) >= limit:
                return findings
    return findings


_CREATE_ALL_RE = re.compile(r"\bmetadata\s*\.\s*create_all\s*\(")
_TABLENAME_RE = re.compile(r"^\s*__tablename__\s*=", re.M)


def find_unregistered_models(code_dir: Path) -> list[dict[str, Any]]:
    """Models that ``create_all()`` will silently skip.

    SQLAlchemy creates tables only for models that have been *imported* by the
    time ``Base.metadata.create_all()`` runs. A product whose main module calls
    create_all without importing its models package gets whichever tables happen
    to be pulled in transitively — and the rest fail at runtime with
    ``no such table``, long after every static check has passed.

    Seen on a live product: login worked because Operator was imported somewhere,
    while /api/operator/spend 500'd on ``no such table: budget_spends``.
    """
    model_modules: list[str] = []
    for file in iter_product_files(code_dir, "*.py"):
        if file.parent.name not in ("models", "model"):
            continue
        if file.name == "__init__.py":
            continue
        try:
            if _TABLENAME_RE.search(file.read_text(encoding="utf-8", errors="replace")):
                model_modules.append(file.stem)
        except OSError:
            continue
    if not model_modules:
        return []

    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _CREATE_ALL_RE.search(text):
            continue
        # Importing the package (or a star/aggregate import of it) registers every
        # model its __init__ pulls in; that is the idiomatic fix.
        imports_package = bool(
            # from app.models import X   /  from ..models import X
            re.search(r"^\s*from\s+[\w.]*models\s+import\b", text, re.M)
            # import app.models
            or re.search(r"^\s*import\s+[\w.]*models\b", text, re.M)
            # from app.models.budget_spend import BudgetSpend
            or re.search(r"^\s*from\s+[\w.]*models\.[\w.]+\s+import\b", text, re.M)
            # from app import models  — the package arrives as a name, not a path
            or re.search(r"^\s*from\s+[\w.]+\s+import\s+[^\n]*\bmodels\b", text, re.M)
        )
        if imports_package:
            continue
        findings.append(
            {
                "file": file.relative_to(code_dir).as_posix(),
                "models": sorted(model_modules)[:10],
            }
        )
    return findings


def find_orm_schema_never_created(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """SQLAlchemy models declared, and nothing ever creates their tables.

    The most expensive single defect of this product's night, and invisible to every gate that
    existed. The browser reported ``500`` on ``POST /api/auth/login``; the login handler was
    correct; four rounds edited it anyway. What actually happened:

    * ``models/user.py`` declares ``User`` on ``Base``;
    * ``main.py`` has no ``Base.metadata.create_all``, no startup hook, no Alembic;
    * so ``users`` does not exist, and every request that touches the database raises
      ``OperationalError: no such table: users`` — a 500.

    The demo journey passed throughout, because the login handler answers demo credentials from the
    environment *before* it queries anything. So the product looked authenticated end to end while
    its database had no schema at all.

    A finding that says "500 somewhere" is unexecutable. This one names the file, the missing call
    and the reason, and it is static — no browser, no server, no flake.
    """
    base_names: set[str] = set()
    model_files: dict[str, list[str]] = {}
    creates_schema: list[str] = []
    migration_files: list[str] = []
    runs_migrations: list[str] = []

    # Existing migrations are not a schema. Measured on the live product: backend/alembic/ held
    # 0001_initial.py, and nothing anywhere ran `alembic upgrade` — not the Dockerfile, not
    # docker-compose, not an entrypoint, and main.py had no startup hook at all. So the tables
    # described in the migration never existed at runtime, and every DB request was a 500.
    for file in iter_product_files(code_dir, "*"):
        rel = file.relative_to(code_dir).as_posix()
        if file.suffix in (".sh", ".yml", ".yaml", ".toml", ".cfg") or file.name in (
            "Dockerfile", "Makefile", "Procfile", "entrypoint.sh", "start.sh",
        ):
            try:
                blob = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                blob = ""
            if re.search(r"alembic\s+upgrade", blob):
                runs_migrations.append(rel)
        if file.name == "alembic.ini" or "/versions/" in f"/{rel}":
            migration_files.append(rel)
            continue
        if file.suffix != ".py":
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r"(\w+)\s*=\s*declarative_base\s*\(", text):
            base_names.add(match.group(1))
        for match in re.finditer(r"class\s+(\w+)\s*\(\s*DeclarativeBase\s*\)", text):
            base_names.add(match.group(1))
        # Only a CALL counts. Importing alembic, or a module named alembic/env.py mentioning it,
        # creates no table — the previous version of this check accepted the mere word and so it
        # stayed silent on a product whose database had no schema at all.
        if re.search(r"\.metadata\.create_all\s*\(", text):
            creates_schema.append(rel)
        if re.search(r"command\.upgrade\s*\(|\brun_migrations\s*\(", text) and "/alembic/" not in f"/{rel}":
            runs_migrations.append(rel)
        tables = re.findall(r"__tablename__\s*=\s*[\"']([\w]+)[\"']", text)
        if tables:
            model_files[rel] = tables

    if not model_files or creates_schema or runs_migrations:
        return []
    if not base_names:
        return []

    # Where the fix belongs: the app entrypoint if there is one, else the module holding the engine.
    entry = ""
    for candidate in ("backend/app/main.py", "app/main.py", "main.py", "backend/main.py"):
        if (code_dir / candidate).is_file():
            entry = candidate
            break
    if not entry:
        for rel in sorted(model_files):
            entry = rel
            break

    all_tables = sorted({tbl for tables in model_files.values() for tbl in tables})
    findings = [
        {
            "code": "orm_schema_never_created",
            "severity": "critical",
            "file": entry,
            "tables": all_tables,
            "model_files": sorted(model_files),
            "migration_files": migration_files[:4],
            "detail": (
                f"{len(all_tables)} table(s) are declared on the ORM base "
                f"({', '.join(all_tables[:8])}) and NOTHING creates them at runtime: "
                + (
                    f"migrations exist ({', '.join(migration_files[:2])}) but no Dockerfile, "
                    "compose file, entrypoint or startup hook ever runs `alembic upgrade`"
                    if migration_files
                    else "no metadata.create_all call anywhere, and no migrations either"
                )
                + ". Every request that touches the database therefore raises OperationalError: "
                "no such table — which surfaces to the browser as a bare 500, and the login "
                "handler that gets blamed for it is usually correct. Fix it in "
                f"{entry}: add a startup hook that creates the schema before the app serves "
                "traffic — `Base.metadata.create_all(bind=engine)` after importing the models "
                "module (so the tables are registered on the metadata)"
                + (
                    ", or run the migrations there with alembic's command.upgrade"
                    if migration_files
                    else ""
                )
                + ". Do not edit the route handlers — they are not the defect."
            ),
        }
    ]
    return findings[:limit]


def find_duplicate_tablenames(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Model classes that declare a ``__tablename__`` already taken by another class."""
    by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in iter_product_files(code_dir, "*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            table = None
            extend_existing = False
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                if "__tablename__" in names and isinstance(stmt.value, ast.Constant):
                    if isinstance(stmt.value.value, str):
                        table = stmt.value.value
                if "__table_args__" in names:
                    # A dict or a tuple ending in a dict; either way the flag is a keyword.
                    for sub in ast.walk(stmt.value):
                        if isinstance(sub, ast.Constant) and sub.value == "extend_existing":
                            extend_existing = True
                        if isinstance(sub, ast.keyword) and sub.arg == "extend_existing":
                            extend_existing = True
            if table and not extend_existing:
                by_table[table].append(
                    {
                        "file": str(path.relative_to(code_dir)),
                        "line": node.lineno,
                        "model": node.name,
                    }
                )

    findings: list[dict[str, Any]] = []
    for table, decls in sorted(by_table.items()):
        if len(decls) < 2:
            continue
        where = "; ".join(f"{d['model']} in {d['file']}:{d['line']}" for d in decls[:4])
        keep = _canonical_home(table, decls)
        drop = [d for d in decls if d is not keep]
        findings.append(
            {
                "table": table,
                "file": keep["file"],
                "line": keep["line"],
                "models": [d["model"] for d in decls],
                "keep": keep["file"],
                "remove_from": [d["file"] for d in drop],
                "detail": (
                    f"{len(decls)} model classes declare __tablename__ = '{table}': {where}. "
                    "SQLAlchemy raises InvalidRequestError as soon as both are registered "
                    "against one MetaData, so the app does not start at all and every "
                    "endpoint is unreachable — no import check sees this because each module "
                    "is fine on its own. "
                    f"KEEP the declaration in {keep['file']} and DELETE "
                    + ", ".join(f"{d['model']} from {d['file']}" for d in drop)
                    + ", re-pointing whatever imported it at "
                    f"{keep['file']}. Do not paper over it with extend_existing=True, which "
                    "silently lets two definitions fight over the same columns."
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings
