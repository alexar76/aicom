"""Classes and calls: forward references in class bodies, instance attributes nothing sets,
keyword arguments a callee does not take.
"""

from __future__ import annotations

import ast
import builtins
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.code_discovery import iter_product_files

from .common import (
    _module_path,
    _normalised_matches,
    from_imports_with_aliases,
    MAX_FINDINGS,
    resolve_import_target,
)


def find_class_body_forward_refs(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Class-body statements that read a name the body has not bound yet.

    Python executes a class body top to bottom, so this raises ``NameError`` the moment the module is
    imported::

        class AtlasClient:
            invoke = invoke_capability          # <- line 8: nothing has bound this yet
            async def invoke(self, capability, payload):
                return await self.invoke_capability(capability, payload)

    The round wrote both halves of a fix and left the failed first half in place. The second is correct;
    the first stops the app from importing at all.

    Nothing saw it. ``undefined_names_in_source`` returned ``[]`` and the tree scored **0**, because a
    scope-wide name collector finds ``invoke_capability`` in the class namespace and never asks whether
    it was bound *before* the line that reads it. That blindness deadlocked the product: with the score
    at zero, any fix to the file measured as no improvement while any incidental change measured as
    risk, so the round guard gave the fix back every single time — three rounds running, on the one
    defect standing between the product and booting.

    Only class-body execution counts. A name read inside a method resolves when the method is called,
    which is a different question and not this one; a decorator or a default argument, however, is
    evaluated with the body and does count.
    """
    findings: list[dict[str, Any]] = []
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (SyntaxError, OSError, ValueError):
            continue

        # MODULE scope only. Walking the whole tree pulled method names into it, so
        # `invoke = invoke_capability` inside a class looked bound by the very method defined below it
        # — which is exactly the case this detector exists for, and it went silent on it.
        module_bound: set[str] = set(dir(builtins))
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    module_bound.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                module_bound.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For, ast.With, ast.Try)):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        module_bound.add(sub.id)
                    elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        module_bound.add(sub.name)
            elif isinstance(node, (ast.If, ast.While)):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        module_bound.add(sub.id)

        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            bound: set[str] = set(module_bound)
            # A generic class parameter or an enclosing name is fine; only ordering is in question.
            for stmt in cls.body:
                # Read the statement first, then record what it binds — that ordering IS the check.
                # Names a lambda parameter or a comprehension target binds are local to it. Without
                # this, `Column(default=lambda x: ...)` in a model body read as five critical findings
                # about a name called `x`.
                local: set[str] = set()
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Lambda):
                        args = sub.args
                        for arg in (
                            list(args.posonlyargs or [])
                            + list(args.args or [])
                            + list(args.kwonlyargs or [])
                            + [a for a in (args.vararg, args.kwarg) if a is not None]
                        ):
                            local.add(arg.arg)
                    elif isinstance(sub, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                        for gen in sub.generators:
                            for name in ast.walk(gen.target):
                                if isinstance(name, ast.Name):
                                    local.add(name.id)
                    elif isinstance(sub, ast.ExceptHandler) and sub.name:
                        local.add(sub.name)

                reads: list[ast.Name] = []
                for sub in ast.walk(stmt):
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not stmt:
                        continue
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                        if sub.id not in local:
                            reads.append(sub)
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Its body runs later; only decorators and defaults run now.
                    reads = [
                        n
                        for dec in stmt.decorator_list
                        for n in ast.walk(dec)
                        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                    ] + [
                        n
                        for default in (stmt.args.defaults or []) + [
                            d for d in (stmt.args.kw_defaults or []) if d is not None
                        ]
                        for n in ast.walk(default)
                        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                    ]
                for name in reads:
                    if name.id in bound:
                        continue
                    findings.append(
                        {
                            "code": "class_body_forward_ref",
                            "severity": "critical",
                            "file": file.relative_to(code_dir).as_posix(),
                            "line": name.lineno,
                            "class": cls.name,
                            "name": name.id,
                            "detail": (
                                f"{file.relative_to(code_dir).as_posix()}:{name.lineno} reads "
                                f"'{name.id}' in the body of class {cls.name} before anything binds it. "
                                "A class body executes top to bottom at import, so Python raises "
                                f"NameError: name '{name.id}' is not defined and the app never starts. "
                                "If this line was meant to alias a method defined lower down, delete it "
                                "— a method defined later cannot be referenced here; the wrapper method "
                                "below already does the job."
                            ),
                        }
                    )
                    if len(findings) >= limit:
                        return findings
                # Now record the bindings this statement makes.
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    bound.add(stmt.name)
                else:
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                            bound.add(sub.id)
                        elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                            bound.add(sub.target.id)
    return findings


# Names pydantic/BaseModel and ordinary objects carry without declaring them in a class body.
# Reading one of these is never the defect this detector is looking for.
# Third-party bases whose attributes are still declared in the subclass body, so a subclass of one
# remains analysable. Pydantic is the whole reason this list exists: its fields ARE the class body,
# and treating `BaseSettings` as an opaque base made the detector silent on exactly the case it was
# written for — `class Settings(BaseSettings)` with 19 declared fields and `settings.cors_origins`
# read in main.py. Anything not listed here makes its subclass unanalysable, because an unknown base
# may well provide the attribute and a false critical costs more than a miss.
_ANALYSABLE_FOREIGN_BASES = frozenset({"BaseSettings", "BaseModel", "object"})

_INHERITED_ATTRS = frozenset(
    {
        "model_config", "model_fields", "model_fields_set", "model_computed_fields",
        "model_dump", "model_dump_json", "model_copy", "model_validate",
        "model_validate_json", "model_json_schema", "model_extra", "model_post_init",
        "dict", "json", "copy", "schema", "schema_json", "parse_obj", "parse_raw",
        "construct", "validate", "fields", "Config", "metadata", "registry", "query",
    }
)


def find_missing_instance_attributes(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Attributes read off a module-level singleton that its class never declares.

    The shape is ubiquitous in generated FastAPI code and fatal at import time::

        app/config.py:  class Settings(BaseSettings):  # 21 fields, none of them cors_origins
                        settings = Settings()
        app/main.py:19: allow_origins=settings.cors_origins

    ``AttributeError: 'Settings' object has no attribute 'cors_origins'`` before the first route is
    registered, so the app never starts and every endpoint is unreachable. Nothing static had an
    opinion: the module imports cleanly, every name resolves, the class exists. It surfaced only as
    a uvicorn traceback in the demo-journey log — the same blind spot as missing symbols and missing
    modules, one level further in, at the instance rather than the module.

    Kept narrow on purpose, because this reports ``critical`` and criticals decide whether a round's
    work is kept:

    * only module-level ``name = ClassName()`` singletons whose class is defined in this product;
    * classes that synthesise attributes (``__getattr__``) or accept extras (pydantic
      ``extra = "allow"``) are skipped — there the read may well succeed;
    * attributes assigned onto the singleton anywhere in the tree count as declared;
    * dunders and the inherited pydantic/ORM API are never reported.
    """
    # Keyed by the module that creates it, not by name alone: two modules can each bind `settings`
    # to different objects, and conflating them accused `settings.anything` on an `object()` in an
    # unrelated file. A false critical costs more than a miss on a gate that discards work.
    singletons: dict[tuple[str, str], str] = {}   # (module, binding name) -> class name
    classes: dict[str, dict[str, Any]] = {}  # class name -> {names, bases, dynamic, file}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        rel = file.relative_to(code_dir).as_posix()
        module_here = _module_path(file, code_dir)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names: set[str] = set()
                dynamic = False
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        names.add(stmt.target.id)
                    elif isinstance(stmt, ast.Assign):
                        names.update(x.id for x in stmt.targets if isinstance(x, ast.Name))
                    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names.add(stmt.name)
                        if stmt.name in ("__getattr__", "__getattribute__"):
                            dynamic = True
                    elif isinstance(stmt, ast.ClassDef):
                        names.add(stmt.name)
                        # `class Config: extra = "allow"` lets undeclared fields through.
                        for inner in stmt.body:
                            if isinstance(inner, ast.Assign) and isinstance(
                                inner.value, ast.Constant
                            ):
                                if inner.value.value == "allow":
                                    dynamic = True
                    if isinstance(stmt, ast.Assign):
                        for sub in ast.walk(stmt):
                            if isinstance(sub, ast.keyword) and sub.arg == "extra":
                                if isinstance(sub.value, ast.Constant) and sub.value.value == "allow":
                                    dynamic = True
                classes[node.name] = {
                    "names": names,
                    # Which members are coroutines: calling one without await yields
                    # "TypeError: 'coroutine' object is not subscriptable", a shape that cost this
                    # product several rounds while the finding said nothing about it.
                    "async_names": {
                        stmt.name
                        for stmt in node.body
                        if isinstance(stmt, ast.AsyncFunctionDef)
                    },
                    "bases": [b.id for b in node.bases if isinstance(b, ast.Name)],
                    "dynamic": dynamic,
                    "file": rel,
                    "line": node.lineno,
                }
        # Module-level singletons AND locals built from a product class. The local case was missed
        # and it cost a boot: `heartbeat = HeartbeatService(db)` inside a lifespan function, followed
        # by `heartbeat.scheduler.shutdown()` on a class that has start(), stop(), _thread and
        # _stop_event — and no scheduler. AttributeError inside lifespan takes the whole app down,
        # exactly like the module-level case this detector was written for; the only difference is
        # the indentation of the line that builds the object.
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                call = node.value
                if (
                    isinstance(target, ast.Name)
                    and isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                ):
                    key = (module_here, target.id)
                    prior = singletons.get(key)
                    if prior is not None and prior != call.func.id:
                        # The same name bound to two different classes in one module: two locals in
                        # separate functions, most likely. Which class a read belongs to is no longer
                        # knowable from this analysis, and a wrong critical costs a round's work.
                        singletons[key] = ""
                    elif prior != "":
                        singletons[key] = call.func.id

    def _offer(class_name: str, wanted: str) -> str:
        """"It does not declare X" is a diagnosis; "it declares these three" is an instruction.

        Without this the rounds oscillated: `atlas.get_advisory(...)` does not exist, so one round
        added a method, the next deleted the call, a third put the placeholder back — while
        AtlasClient had get_situation_brief, get_fire_weather and get_nearest_read sitting right
        there, every one of them async. Naming them, nearest spelling first, turns three rounds of
        guessing into one edit.
        """
        import difflib

        info = classes.get(class_name) or {}
        names = {
            n for n in (info.get("names") or set())
            if isinstance(n, str) and not n.startswith("_")
        }
        if not names:
            return ""
        close = difflib.get_close_matches(wanted, sorted(names), n=3, cutoff=0.4)
        listed = close or sorted(names)[:6]
        asyncs = info.get("async_names") or set()
        note = ""
        if any(n in asyncs for n in listed):
            note = (
                " (async — call with await; calling one without await gives "
                "\"TypeError: 'coroutine' object is not subscriptable\" instead)"
            )
        return (
            f"{class_name} DOES declare: {', '.join(listed)}{note}. "
            f"If one of those is the method you meant, call it instead. "
        )

    def declared(class_name: str, seen: set[str] | None = None) -> set[str] | None:
        if not class_name:
            return None
        """Every name the class and its product-defined bases declare, or None if unanalysable."""
        seen = seen or set()
        if class_name in seen:
            return set()
        info = classes.get(class_name)
        if info is None:
            # A class we do not own — FastAPI, TestClient, CryptContext — is unanalysable, and
            # treating "not found" as "declares nothing" accused every one of them: app.get,
            # client.post, pwd_context.hash. Fourteen false criticals from one wrong default, on a
            # gate that decides whether a round's work is thrown away.
            #
            # Pydantic is the exception, and not a grudging one: its fields are the class body, so a
            # BaseSettings subclass is exactly as readable as one with no base at all.
            return set() if class_name in _ANALYSABLE_FOREIGN_BASES else None
        if info["dynamic"]:
            return None
        seen.add(class_name)
        out = set(info["names"])
        for base in info["bases"]:
            more = declared(base, seen)
            if more is None:
                return None
            out |= more
        return out

    # An attribute assigned onto the singleton anywhere counts as declared.
    assigned: dict[str, set[str]] = defaultdict(set)
    reads: dict[tuple[str, str], list[str]] = defaultdict(list)
    attr_class: dict[tuple[str, str], str] = {}
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (SyntaxError, OSError, ValueError):
            continue
        rel = file.relative_to(code_dir).as_posix()
        importer_module = _module_path(file, code_dir)
        # In scope here means: created in this module, or imported FROM the module that creates it.
        in_scope: dict[str, str] = {
            name: cls for (mod, name), cls in singletons.items() if mod == importer_module
        }
        for written_mod, pairs in from_imports_with_aliases(text):
            target_module = resolve_import_target(written_mod, importer_module)
            for name, alias in pairs:
                cls = singletons.get((target_module, name)) or singletons.get(
                    (f"{target_module}.__init__", name)
                )
                if cls:
                    in_scope[alias or name] = cls
        if not in_scope:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
                continue
            base = node.value.id
            if base not in in_scope:
                continue
            if isinstance(node.ctx, ast.Load) and in_scope[base] not in classes:
                continue
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                assigned[base].add(node.attr)
                continue
            if node.attr.startswith("__") or node.attr in _INHERITED_ATTRS:
                continue
            reads[(base, node.attr)].append(f"{rel}:{node.lineno}")
            attr_class[(base, node.attr)] = in_scope[base]

    import difflib

    findings: list[dict[str, Any]] = []
    for (base, attr), where in sorted(reads.items(), key=lambda kv: -len(kv[1])):
        class_name = attr_class[(base, attr)]
        if class_name not in classes:
            # Only a class this product defines can be judged. `x = object()` or any library
            # constructor is not ours to have an opinion about.
            continue
        known = declared(class_name)
        if known is None or attr in known or attr in assigned.get(base, ()):
            continue
        info = classes.get(class_name) or {}
        # Case and underscore differences first — `ATLAS_BASE_URL` against `atlas_base_url` is the
        # commonest shape of this mistake and difflib cannot see it at all.
        near = _normalised_matches(attr, known)
        # Then prefix relations: `invoke` against `invoke_capability` also scores below any sane
        # difflib cutoff, and yet it is the answer — the round wrote a short alias for a method
        # that exists under a longer name.
        near += [
            k for k in sorted(known)
            if (k.startswith(attr) or attr.startswith(k)) and k not in near
        ][:2]
        near += [
            k
            for k in difflib.get_close_matches(attr, sorted(known), n=2, cutoff=0.7)
            if k not in near
        ]
        near = near[:2]
        findings.append(
            {
                "code": "missing_attribute",
                "severity": "critical",
                "singleton": base,
                "attribute": attr,
                "file": info.get("file", ""),
                "line": info.get("line"),
                "readers": sorted(set(where))[:6],
                "did_you_mean": near,
                "detail": (
                    f"{class_name} never declares '{attr}', read as {base}.{attr} at "
                    + ", ".join(sorted(set(where))[:4])
                    + f". Python raises AttributeError: '{class_name}' object has no attribute "
                    f"'{attr}' the first time that line runs — at import for module-level code — so "
                    f"the app does not start. {_offer(class_name, attr)}"
                    "Do NOT delete the call site to silence this — the call is what the product "
                    f"does. Otherwise declare it on {class_name} in "
                    f"{info.get('file', 'its module')}."
                    + (f" Did you mean {', '.join(near)}?" if near else "")
                ),
            }
        )
        if len(findings) >= limit:
            break
    return findings


def _callable_kwargs(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[set[str], bool]:
    """Keyword names a product method accepts, and whether it has ``**kwargs``."""
    args = fn.args
    names = {a.arg for a in args.posonlyargs + args.args if a.arg not in {"self", "cls"}}
    names |= {a.arg for a in args.kwonlyargs}
    return names, args.kwarg is not None


def find_unexpected_keyword_arguments(code_dir: Path, limit: int = MAX_FINDINGS) -> list[dict[str, Any]]:
    """Call site passes a keyword the method does not declare.

    The live Sentinel deploy answered 200 with UNKNOWN because::

        await atlas.get_situation_brief(west=west, east=east, south=south, north=north)

    while AtlasClient.get_situation_brief(self, lat, lon) — TypeError, swallowed by
    ``except Exception``. missing_attribute is silent: the method exists. The mesh
    contract is silent: the envelope is built inside the client, never at the call.
    """
    methods: dict[str, dict[str, tuple[set[str], bool, str, int]]] = {}
    classes_file: dict[str, str] = {}
    singletons: dict[tuple[str, str], str] = {}

    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (SyntaxError, OSError, ValueError):
            continue
        rel = file.relative_to(code_dir).as_posix()
        module_here = _module_path(file, code_dir)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            slot: dict[str, tuple[set[str], bool, str, int]] = {}
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    accepted, has_kw = _callable_kwargs(stmt)
                    slot[stmt.name] = (accepted, has_kw, rel, stmt.lineno)
            methods[node.name] = slot
            classes_file[node.name] = rel
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                call = node.value
                if (
                    isinstance(target, ast.Name)
                    and isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id in methods
                ):
                    singletons[(module_here, target.id)] = call.func.id

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for file in iter_product_files(code_dir, "*.py"):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (SyntaxError, OSError, ValueError):
            continue
        rel = file.relative_to(code_dir).as_posix()
        importer_module = _module_path(file, code_dir)
        in_scope: dict[str, str] = {
            name: cls for (mod, name), cls in singletons.items() if mod == importer_module
        }
        for written_mod, pairs in from_imports_with_aliases(text):
            target_module = resolve_import_target(written_mod, importer_module)
            for name, alias in pairs:
                cls = singletons.get((target_module, name)) or singletons.get(
                    (f"{target_module}.__init__", name)
                )
                if cls:
                    in_scope[alias or name] = cls
                # `from ..services.atlas_client import AtlasClient` then `atlas = AtlasClient()`
                if (alias or name) in methods:
                    in_scope[alias or name] = alias or name
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
            ):
                func = node.value.func
                cls_name = None
                if isinstance(func, ast.Name) and func.id in methods:
                    cls_name = func.id
                elif isinstance(func, ast.Attribute) and func.attr in methods:
                    cls_name = func.attr
                if cls_name:
                    in_scope[node.targets[0].id] = cls_name
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name):
                continue
            obj = node.func.value.id
            method = node.func.attr
            class_name = in_scope.get(obj)
            if not class_name or class_name not in methods:
                continue
            sig = methods[class_name].get(method)
            if not sig:
                continue
            accepted, has_kw, class_file, _def_line = sig
            if has_kw:
                continue
            for kw in node.keywords:
                if not kw.arg or kw.arg in accepted:
                    continue
                key = (rel, method, kw.arg, class_name)
                if key in seen:
                    continue
                seen.add(key)
                offered = ", ".join(sorted(accepted)) or "(none besides self)"
                findings.append(
                    {
                        "code": "unexpected_keyword_argument",
                        "severity": "critical",
                        "file": rel,
                        "line": node.lineno,
                        "class_file": class_file,
                        "class": class_name,
                        "method": method,
                        "keyword": kw.arg,
                        "detail": (
                            f"{class_name}.{method}() does not accept keyword '{kw.arg}', "
                            f"called as {obj}.{method}({kw.arg}=...) at {rel}:{node.lineno}. "
                            f"The method is defined in {class_file} with parameters: {offered}. "
                            f"Python raises TypeError: {class_name}.{method}() got an unexpected "
                            f"keyword argument '{kw.arg}' the first time that line runs. A "
                            "`except Exception` that returns {\"level\": \"UNKNOWN\"} hides it as "
                            "a 200 forever — that is the defect that shipped on Vercel. Change "
                            f"the call in {rel} to match the signature, or change the signature in "
                            f"{class_file}. Do NOT swallow TypeError into UNKNOWN."
                        ),
                    }
                )
                if len(findings) >= limit:
                    return findings
    return findings
