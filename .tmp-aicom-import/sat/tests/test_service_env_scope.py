"""Each service gets the settings it reads, and nothing it does not.

scripts/security/service_env.py cuts the shared `.env` into one file per service. An
allow-list that drops a name the service reads is worse than the leak it prevents: the
service still starts, and quietly falls back to a default (public RPCs instead of the
operator's node, SQLite instead of Postgres, checkout answering 503). So the lists are not
trusted here. This file reads each service's code and compose files, collects every
environment name they read, and fails when the filter would drop one.

A name a service reads but must still NOT get is withheld in service_env.DENY, with the
reason next to it. A name the scan finds that the running service never reads (an offline
tool shipped in the same image) is listed in NOT_READ_AT_RUNTIME below, also with a reason.
Nothing else may be left out.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import stat
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / "scripts" / "security"
sys.path.insert(0, str(SECURITY))
import service_env  # noqa: E402

NAME = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")
PREFIX = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_")
# Helper names like _env, env_bool, _env_int, deep_env_int, _envi, _truthy_env — but not
# envelope, environment or load_dotenv.
ENV_HELPER = re.compile(r"(?:^|_)env[a-z]?(?:$|_)")
SKIP_DIRS = {"tests", "test", "__tests__", "e2e", "node_modules", ".venv", "venv", "__pycache__"}

# ── What runs in each container ────────────────────────────────────────────────────────
# The Factory image is the whole monorepo, so a directory scan would claim every satellite.
# Follow imports instead, from what entrypoint.sh and deploy.sh actually start; the
# Factory's own packages are scanned whole as well, because they load modules by name.
FACTORY_ENTRY_POINTS = [
    "web/backend/main.py", "pipeline_worker.py", "director/worker.py", "main.py",
    "security/bootstrap_secrets.py", "security/bootstrap_admin.py", "security/prod_startup_guard.py",
    "llm/startup_provider_sync.py", "llm/persist_deepseek.py", "orchestrator/migrate.py",
    "scripts/materialize_all_spec_landings.py", "scripts/ensure_config_overlay.py",
    "scripts/set_auto_pipeline.py", "scripts/apply_pipeline_db_config.py",
]
FACTORY_PACKAGES = ["web/backend", "core", "orchestrator", "agents", "llm", "security", "director"]
# The Factory installs aimarket-hub as a package (Dockerfile) and imports chain_net from it.
IMPORT_ROOTS = [ROOT, ROOT / "aimarket-hub"]
# Next.js server code: runs inside `app` (all-in-one) and inside the split `frontend`.
FRONTEND_RUNTIME = ["web/frontend/app", "web/frontend/components", "web/frontend/lib",
                    "web/frontend/hooks", "web/frontend/proxy.ts", "web/frontend/next.config.js"]
# Exactly what aimarket-hub/Dockerfile copies or installs.
HUB_IMAGE = ["aimarket-hub/aimarket_hub", "acex", "plugins", "awr/reference/python",
             "aimarket-hub/plugins/aimarket-provenance"]
ATLAS_IMAGE = ["atlas/atlas"]
MONITOR_IMAGE = ["alien-monitor/backend"]

TEMPLATES = [".env.example", ".env.vps.example", "deploy/hub-payment.env.example",
             "deploy/hub-zk.env.example"]

# Names the scan finds in a service's image that the running service never reads.
NOT_READ_AT_RUNTIME = {
    "factory": {
        # scripts/set_auto_pipeline.py is handed it by entrypoint.sh (`export
        # AUTO_PIPELINE_VALUE=...` from AIFACTORY_AUTONOMOUS_PIPELINE) or by `docker compose
        # exec ... env AUTO_PIPELINE_VALUE=0`; never from .env.
        "AUTO_PIPELINE_VALUE",
        # Set by `next build` itself to tell build from serve; an operator value would lie.
        "NEXT_PHASE",
    },
    "frontend": {"NEXT_PHASE"},  # as above
    "hub": {
        # acex/scripts/pulse_amm_create_pool_plan.py, an offline operator tool that happens to
        # ship in the image (COPY acex/), falls back to it. Nothing the hub serves reads it.
        "PRIVATE_KEY",
    },
}
# Provider YAMLs each image ships: the LLM router reads the key named by `api_key_env`.
PROVIDER_CONFIGS = {
    "factory": ["data/config/model_providers.example.yaml"],
    "atlas": ["atlas/config/model_providers.example.yaml"],
}


# ── Scanners ────────────────────────────────────────────────────────────────────────────
def _name_of(node) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _reads_environ_directly(call: ast.Call) -> bool:
    fname = _name_of(call.func)
    owner = _name_of(call.func.value) if isinstance(call.func, ast.Attribute) else ""
    return fname == "getenv" or (owner == "environ" and fname in {"get", "pop", "setdefault"})


def _leading_prefix(node):
    if isinstance(node, ast.JoinedStr) and node.values and isinstance(node.values[0], ast.Constant):
        head = node.values[0].value
        if isinstance(head, str) and PREFIX.fullmatch(head):
            return head
    return None


@lru_cache(maxsize=None)
def _python_file(path: Path):
    """(names read, env-shaped literals, dynamic prefixes read, name tables) for one file."""
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return frozenset(), frozenset(), frozenset(), frozenset()
    names, literals, prefixes, tables = set(), set(), set(), set()
    # Functions in this file that read the environment through a variable — pick(*names),
    # _first_env(keys) — count as readers at their call sites in the same file.
    helpers = set()
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Call) and _reads_environ_directly(sub) and sub.args \
                        and not isinstance(sub.args[0], ast.Constant):
                    helpers.add(fn.name)
    walks_environ = "os.environ.items()" in source or "os.environ.keys()" in source
    # DEPOSIT_CLAIMS_DIR_ENV = "AIMARKET_DEPOSIT_CLAIMS_DIR", then os.environ.get(DEPOSIT_CLAIMS_DIR_ENV):
    # the name only appears in the assignment, so resolve the constant at the read.
    consts = {t.id: stmt.value.value for stmt in ast.walk(tree) if isinstance(stmt, ast.Assign)
              and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
              and NAME.fullmatch(stmt.value.value) for t in stmt.targets if isinstance(t, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and NAME.fullmatch(node.value):
            literals.add(node.value)
        # A file that reads the environment through a variable usually takes the names from
        # a table: chain_net's {"base": ("BASE_RPC_URL", "AIFACTORY_PAYMENT_RPC_BASE")}.
        if helpers and isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            row = frozenset(e.value for e in node.elts if isinstance(e, ast.Constant)
                            and isinstance(e.value, str) and NAME.fullmatch(e.value))
            if row:
                tables.add(row)
        # chain_net builds f"AIMARKET_ADDR_{chain}_" and matches it against os.environ.
        if walks_environ and _leading_prefix(node):
            prefixes.add(_leading_prefix(node))
        # pydantic-settings with env_prefix: every annotated field is PREFIX + FIELD.
        if isinstance(node, ast.ClassDef):
            prefix = next((kw.value.value for sub in ast.walk(node) if isinstance(sub, ast.Call)
                           for kw in sub.keywords if kw.arg == "env_prefix"
                           and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)), None)
            if prefix:
                names.update(prefix + stmt.target.id.upper() for stmt in node.body
                             if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
                             and stmt.target.id != "model_config")
        if isinstance(node, ast.Call):
            fname = _name_of(node.func)
            if _reads_environ_directly(node):
                args = node.args[:1]
            elif ENV_HELPER.search(fname.lower()) or fname in helpers:
                args = node.args
            else:
                args = []
            for arg in args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and NAME.fullmatch(arg.value):
                    names.add(arg.value)
                elif isinstance(arg, ast.Name) and arg.id in consts:
                    names.add(consts[arg.id])
                elif _leading_prefix(arg):
                    prefixes.add(_leading_prefix(arg))
            if fname == "startswith" and walks_environ and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and PREFIX.fullmatch(arg.value):
                    prefixes.add(arg.value)
            for kw in node.keywords:
                # pydantic-settings: Field(alias="NAME") and env_prefix="ATLAS_".
                if kw.arg in {"alias", "validation_alias"} and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str) and NAME.fullmatch(kw.value.value):
                    names.add(kw.value.value)
                if kw.arg == "env_prefix" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str) and PREFIX.fullmatch(kw.value.value):
                    prefixes.add(kw.value.value)
        if isinstance(node, ast.Subscript) and _name_of(node.value) == "environ":
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                names.add(node.slice.value)
            elif isinstance(node.slice, ast.Name) and node.slice.id in consts:
                names.add(consts[node.slice.id])
            elif _leading_prefix(node.slice):
                prefixes.add(_leading_prefix(node.slice))
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Constant) \
                and any(_name_of(c) == "environ" for c in node.comparators):
            if isinstance(node.left.value, str):
                names.add(node.left.value)
    return frozenset(names), frozenset(literals), frozenset(prefixes), frozenset(tables)


def _python_files(dirs) -> set[Path]:
    out = set()
    for d in dirs:
        base = ROOT / d
        candidates = [base] if base.is_file() else base.rglob("*.py")
        for path in candidates:
            if not SKIP_DIRS & set(path.relative_to(ROOT).parts):
                out.add(path)
    return out


def _module_file(module: str):
    parts = module.split(".")
    for root in IMPORT_ROOTS:
        base = root.joinpath(*parts)
        if base.with_suffix(".py").is_file():
            return base.with_suffix(".py")
        if (base / "__init__.py").is_file():
            return base / "__init__.py"
    return None


def _package_of(path: Path):
    for root in IMPORT_ROOTS:
        try:
            parts = list(path.relative_to(root).with_suffix("").parts)
        except ValueError:
            continue
        if parts[-1] == "__init__":
            return parts[:-1], True
        return parts, False
    return None, False


def _imported_modules(path: Path, tree) -> set[str]:
    parts, is_pkg = _package_of(path)
    out = set()
    for node in ast.walk(tree):
        bases = []
        if isinstance(node, ast.Import):
            bases = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level and parts is not None:
                here = parts if is_pkg else parts[:-1]
                here = here[: len(here) - (node.level - 1)]
                base = ".".join(here + ([node.module] if node.module else []))
            bases = [base] + [f"{base}.{a.name}" if base else a.name for a in node.names]
        elif isinstance(node, ast.Call) and _name_of(node.func) in {"import_module", "__import__"} \
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            bases = [node.args[0].value]
        for name in filter(None, bases):
            pieces = name.split(".")
            out.update(".".join(pieces[:i]) for i in range(1, len(pieces) + 1))
    return out


def _import_closure(entry_points) -> set[Path]:
    seen, todo = set(), [ROOT / e for e in entry_points]
    while todo:
        path = todo.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for module in _imported_modules(path, tree):
            found = _module_file(module)
            if found and found not in seen:
                todo.append(found)
    return seen


TS_READ = re.compile(r"process\.env(?:\.([A-Z_][A-Z0-9_]*)|\[\s*['\"]([A-Z_][A-Z0-9_]*)['\"]\s*\])")


def _ts_reads(dirs) -> set[str]:
    names = set()
    for d in dirs:
        base = ROOT / d
        files = [base] if base.is_file() else [f for ext in ("ts", "tsx", "js", "mjs") for f in base.rglob("*." + ext)]
        for path in files:
            if SKIP_DIRS & set(path.relative_to(ROOT).parts) or ".test." in path.name or ".spec." in path.name:
                continue
            for m in TS_READ.finditer(path.read_text(encoding="utf-8", errors="replace")):
                names.add(m.group(1) or m.group(2))
    return names


def _shell_reads(path: Path) -> set[str]:
    """Upper-case names a shell script expands without assigning them first."""
    text = path.read_text(encoding="utf-8")
    code = "\n".join(line.split("#", 1)[0] if not line.lstrip().startswith("#!") else "" for line in text.splitlines())
    assigned = set(re.findall(r"(?:^|[\s;(])(?:export\s+|local\s+)?([A-Z][A-Z0-9_]*)=", code, re.MULTILINE))
    with_default = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)[:?=+-]", code))
    expanded = set(re.findall(r"\$\{?([A-Z][A-Z0-9_]*)", code))
    return {n for n in with_default | (expanded - assigned) if NAME.fullmatch(n)}


@lru_cache(maxsize=None)
def _documented() -> frozenset:
    names = set()
    for template in TEMPLATES:
        for line in (ROOT / template).read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*#?\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", line)
            if m:
                names.add(m.group(1))
    return frozenset(names)


def _python_reads(files):
    names, literals, prefixes, tables = set(), set(), set(), set()
    for path in files:
        a, b, c, d = _python_file(path)
        names |= a
        literals |= b
        prefixes |= c
        tables |= d
    # A documented env name sitting in a table (chain_net's legacy RPC names, a tuple of
    # provider keys looped over) is read too, even though no call names it directly — and
    # so is the rest of a table that holds one. A tuple of pipeline stage names is not.
    names |= literals & _documented()
    for row in tables:
        if row & (names | _documented()):
            names |= row
    return names, prefixes


def _provider_keys(service: str) -> set[str]:
    names = set()
    for path in PROVIDER_CONFIGS.get(service, ()):
        names |= set(re.findall(r"api_key_env:\s*['\"]?([A-Z][A-Z0-9_]*)", (ROOT / path).read_text(encoding="utf-8")))
    return names


@lru_cache(maxsize=None)
def service_reads(service: str):
    """(names, dynamic prefixes) the service's own code reads."""
    if service == "factory":
        files = _import_closure(FACTORY_ENTRY_POINTS) | _python_files(FACTORY_PACKAGES)
        names, prefixes = _python_reads(files)
        names |= _ts_reads(FRONTEND_RUNTIME) | _shell_reads(ROOT / "entrypoint.sh")
    elif service == "frontend":
        names, prefixes = _ts_reads(FRONTEND_RUNTIME), set()
    else:
        image = {"hub": HUB_IMAGE, "atlas": ATLAS_IMAGE, "alien-monitor": MONITOR_IMAGE}.get(service)
        names, prefixes = _python_reads(_python_files(image)) if image else (set(), set())
    return frozenset(names | _provider_keys(service)), frozenset(prefixes)


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that accepts compose's `!override` / `!reset` merge tags."""


_ComposeLoader.add_multi_constructor(
    "!", lambda loader, suffix, node: (
        loader.construct_sequence(node, deep=True) if isinstance(node, yaml.SequenceNode)
        else loader.construct_mapping(node, deep=True) if isinstance(node, yaml.MappingNode)
        else loader.construct_scalar(node)))


def _compose(path: str) -> dict:
    return yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}


def _env_keys(service: dict) -> set[str]:
    env = service.get("environment") or {}
    if isinstance(env, list):
        return {str(item).split("=", 1)[0] for item in env}
    return {str(k) for k in env}


# Compose files a production or core-tier host starts these services from. The everything
# tier is left out on purpose: its pins exist to overwrite leftovers, not because the
# service reads them (see its own comments), and no rollout ever copies that tier's env.
ROOT_COMPOSE = sorted(p.name for p in ROOT.glob("docker-compose*.yml") if p.name != "docker-compose.everything.yml")
COMPOSE_SERVICES = {
    "factory": ("app", "pipeline-worker", "director-worker"),
    "frontend": ("frontend",),
    "grafana": ("grafana",),
    "alien-monitor": ("alien-monitor",),
    "hub": ("hub",),
}


def compose_set_names(service: str) -> set[str]:
    """Names compose or the deploy scripts put into the container themselves.

    They reach the container without the env file, but rollout_container.py copies the
    live container's whole environment through the same filter, so the filter must keep
    them — otherwise a rollout silently drops BACKEND_MAX_RESTARTS or AICOM_ROLE.
    """
    names = set()
    if service == "atlas":
        return _env_keys(_compose("atlas/docker-compose.yml")["services"]["atlas"])
    for name in ROOT_COMPOSE:
        services = _compose(name).get("services") or {}
        for svc in COMPOSE_SERVICES.get(service, ()):
            names |= _env_keys(services.get(svc) or {})
    if service == "hub":
        for script in ("scripts/deploy_hub.sh", "scripts/deploy_hub_rebuild.sh"):
            names |= set(re.findall(r"-e ([A-Z][A-Z0-9_]*)=", (ROOT / script).read_text(encoding="utf-8")))
        # hub-payment.env / hub-zk.env reach the hub unfiltered on a first deploy, and
        # through the filter on every rebuild after it.
        for template in ("deploy/hub-payment.env.example", "deploy/hub-zk.env.example"):
            names |= set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", (ROOT / template).read_text(encoding="utf-8"), re.MULTILINE))
    return names


SCANNED = ["factory", "frontend", "hub", "atlas", "alien-monitor"]


# ── The allow-lists cover what each service reads ──────────────────────────────────────
@pytest.mark.parametrize("service,known", [
    # One name per defect this file was written for, so a scanner that silently stops
    # finding things fails here instead of passing everything below vacuously.
    ("factory", {"STRIPE_SECRET_KEY", "VERCEL_TOKEN", "BASE_RPC_URL", "TOGETHER_API_KEY",
                 "METIS_URL", "POSTGRES_PASSWORD", "AIFACTORY_PROD", "AIMARKET_DEPOSIT_CLAIMS_DIR"}),
    ("frontend", {"AIFACTORY_ENABLE_HSTS", "AIFACTORY_FRONTEND_CSP", "INTERNAL_API_URL"}),
    ("hub", {"DATABASE_URL", "AIFACTORY_PAYMENT_MIN_CONFIRMATIONS", "BASE_RPC_URL",
             "AIFACTORY_PAYMENT_RPC_BASE", "METIS_URL", "METIS_API_KEY", "OPENROUTER_API_KEY"}),
    ("atlas", {"ATLAS_OPERATOR_TOKEN", "ATLAS_SIGNING_SEED_B64", "ATLAS_CREDITS_ENABLED",
               "DEEPSEEK_API_KEY", "AIFACTORY_PROD"}),
    ("alien-monitor", {"ALIEN_API_TOKEN"}),
])
def test_the_scan_sees_what_the_service_reads(service, known):
    names, _ = service_reads(service)
    assert known <= names, f"the {service} scan no longer finds {sorted(known - names)}"


@pytest.mark.parametrize("service", SCANNED)
def test_every_name_a_service_reads_reaches_it(service):
    names, _ = service_reads(service)
    excused = NOT_READ_AT_RUNTIME.get(service, set()) | service_env.DENY.get(service, set())
    dropped = sorted(n for n in names - excused if not service_env.allowed(service, n))
    assert not dropped, (
        f"service_env.py would drop {len(dropped)} name(s) that {service} reads: {dropped}.\n"
        f"Add each to SCOPES['{service}'] in scripts/security/service_env.py, or, if the "
        f"service must not get it, to DENY with the reason.")


@pytest.mark.parametrize("service", SCANNED)
def test_every_family_a_service_reads_reaches_it(service):
    """`AIMARKET_RPC_<CHAIN>` and friends are read by computed name."""
    _, prefixes = service_reads(service)
    missing = sorted(p for p in prefixes if not service_env.allowed(service, p + "PROBE"))
    assert not missing, f"{service} reads names starting {missing}, and the filter drops them"


@pytest.mark.parametrize("service", SCANNED)
def test_every_allowed_name_is_one_the_service_reads(service):
    """The other direction: the explicit lists are derived, so a name nothing reads is a
    grant nobody asked for (MESH_API_TOKEN sat in the Factory's list with no reader)."""
    reads, _ = service_reads(service)
    _, names = service_env.SCOPES[service]
    families = service_env.PROVIDER_KEYS | service_env.CHAIN  # read by configured or computed name
    unread = sorted(n for n in names - families if n not in reads | compose_set_names(service))
    assert not unread, f"service_env.py grants {service} names it never reads: {unread}"


@pytest.mark.parametrize("service", SCANNED + ["grafana"])
def test_names_the_deploy_sets_survive_a_rollout(service):
    dropped = sorted(n for n in compose_set_names(service) if not service_env.allowed(service, n))
    assert not dropped, f"a rollout of {service} would drop what its compose/deploy sets: {dropped}"


def test_rollout_leaves_image_owned_variables_to_the_new_image():
    """Carrying PATH forward from an older base image is how a rebuilt container ends up
    unable to find python (deploy_hub_rebuild.sh drops these for the same reason)."""
    old_env = ["PATH=/usr/local/bin:/old/venv/bin", "PYTHON_VERSION=3.11.9", "PYTHON_SHA256=abc",
               "GPG_KEY=k", "LANG=C.UTF-8", "HOSTNAME=0123456789ab", "AIMARKET_HUB_NAME=x"]
    for service in ("hub", "factory", "atlas", "frontend"):
        kept = [e.split("=", 1)[0] for e in service_env.filtered(service, old_env)]
        assert not {"PATH", "PYTHON_VERSION", "PYTHON_SHA256", "GPG_KEY", "LANG", "HOSTNAME"} & set(kept), (service, kept)
    assert service_env.filtered("hub", old_env) == ["AIMARKET_HUB_NAME=x"]


# ── ...and nothing that belongs to someone else ─────────────────────────────────────────
MUST_NOT_REACH = {
    "factory": ["AIMARKET_ADMIN_TOKEN", "AIMARKET_ESCROW_PRIVATE_KEY", "AIMARKET_ESCROW_SIGNER_TOKEN",
                "AIMARKET_ESCROW_HUB_KEY", "AIMARKET_PEER_PAYMENT_CHANNEL_SECRET", "AIMARKET_NFT_OWNER_KEY",
                "AIMARKET_FEDERATION_JUDGE_KEY", "AIMARKET_PUBLISH_TOKEN", "AIMARKET_PEER_API_KEYS",
                "AIMARKET_VERIFY_METIS_KEY", "ATLAS_SIGNING_SEED_B64", "ATLAS_OPERATOR_TOKEN",
                "LOTTERY_AGENT_TOKEN", "LOTTERY_OPERATOR_KEY", "ACEX_DEPLOYER_KEY", "ETH_PRIVATE_KEY",
                "MESH_API_TOKEN", "MESH_ADMIN_TOKEN"],
    "hub": ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
            "GROQ_API_KEY", "TOGETHER_API_KEY", "ACEX_DEPLOYER_KEY", "LOTTERY_AGENT_TOKEN",
            "LOTTERY_REP_BONUS_SECRET", "LOTTERY_KEYS", "LOTTERY_OPERATOR_KEY", "HUB_PUBLIC_URL",
            "STRIPE_SECRET_KEY", "CUSTOMER_JWT_SECRET", "JWT_SECRET_KEY", "MESH_API_TOKEN",
            "ATLAS_SIGNING_SEED_B64", "ETH_PRIVATE_KEY", "AIMARKET_WALLET_KEY", "VERCEL_TOKEN"],
    "atlas": ["STRIPE_SECRET_KEY", "AIMARKET_ADMIN_TOKEN", "MESH_API_TOKEN", "CUSTOMER_JWT_SECRET",
              "JWT_SECRET_KEY", "ETH_PRIVATE_KEY", "LOTTERY_OPERATOR_KEY"],
    "frontend": ["DEEPSEEK_API_KEY", "JWT_SECRET_KEY", "CUSTOMER_JWT_SECRET", "MESH_API_TOKEN",
                 "STRIPE_SECRET_KEY", "AIMARKET_WALLET_KEY", "POSTGRES_PASSWORD", "AIFACTORY_ADMIN_PASSWORD"],
    "alien-monitor": ["STRIPE_SECRET_KEY", "ATLAS_SIGNING_SEED_B64", "ETH_PRIVATE_KEY",
                      "AIMARKET_ADMIN_TOKEN", "CUSTOMER_JWT_SECRET", "JWT_SECRET_KEY", "MESH_API_TOKEN"],
    "grafana": ["DEEPSEEK_API_KEY", "STRIPE_SECRET_KEY", "POSTGRES_PASSWORD", "GRAFANA_ADMIN_PASSWORD"],
}


@pytest.mark.parametrize("service,secret", [(s, n) for s, names in MUST_NOT_REACH.items() for n in names])
def test_other_services_secrets_do_not_reach(service, secret):
    assert not service_env.allowed(service, secret), f"{service} would receive {secret}"


# ── Parsing: read .env the way compose does, fail loudly where it cannot ───────────────
def _run(args, cwd=None, env=None):
    return subprocess.run([sys.executable, str(SECURITY / "service_env.py"), *args],
                          capture_output=True, text=True, cwd=cwd, env=env)


def test_compose_legal_forms_are_kept(tmp_path):
    src = tmp_path / "source.env"
    src.write_text(
        "# comment\n"
        "export DEEPSEEK_API_KEY=fake-deepseek\n"
        "  AIFACTORY_INDENTED=fake-indented\n"
        "OPENAI_API_KEY = fake-spaced\n"
        'AIFACTORY_MULTI="line1\nline2"\n'
        "AIFACTORY_AFTER=fake-after\n"
        "STRIPE_SECRET_KEY=first\n"
        "STRIPE_SECRET_KEY=last\n")
    out = tmp_path / "env" / "factory.env"
    result = _run(["factory", str(src), str(out)])
    assert result.returncode == 0, result.stderr
    text = out.read_text()
    for line in ("DEEPSEEK_API_KEY=fake-deepseek", "AIFACTORY_INDENTED=fake-indented",
                 "OPENAI_API_KEY=fake-spaced", 'AIFACTORY_MULTI="line1\nline2"',
                 "AIFACTORY_AFTER=fake-after", "STRIPE_SECRET_KEY=last"):
        assert line in text, line
    assert "STRIPE_SECRET_KEY=first" not in text
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_docker_env_files_refuse_what_docker_cannot_carry(tmp_path):
    """The hub is started with `docker run --env-file`, which has no quoting at all: it read
    the second line of this value as a variable name and gave the hub `"line1` as the value."""
    src = tmp_path / "source.env"
    src.write_text('AIMARKET_OK=1\nAIMARKET_MULTI="line1\nline2"\n')
    result = _run(["hub", str(src), str(tmp_path / "hub.env")])
    assert result.returncode != 0
    assert "AIMARKET_MULTI" in result.stderr and "line1" not in result.stderr
    assert not (tmp_path / "hub.env").exists()


def test_another_services_multiline_value_does_not_block_the_hub(tmp_path):
    src = tmp_path / "source.env"
    src.write_text('OPENAI_API_KEY="line1\nline2"\nAIMARKET_OK=1\n')
    result = _run(["hub", str(src), str(tmp_path / "hub.env")])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "hub.env").read_text() == "AIMARKET_OK=1\n"


def test_docker_env_files_keep_values_as_docker_read_them(tmp_path):
    """The same text `docker --env-file .env` handed the hub before, quotes included."""
    src = tmp_path / "source.env"
    src.write_text('AIMARKET_QUOTED="kept as written"\nAIMARKET_HASH=a # b\n')
    result = _run(["hub", str(src), str(tmp_path / "hub.env")])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "hub.env").read_text() == 'AIMARKET_QUOTED="kept as written"\nAIMARKET_HASH=a # b\n'


def test_a_container_capture_is_read_line_by_line(tmp_path):
    """deploy_hub_rebuild.sh feeds `docker inspect` output. A value there that opens a quote
    (left by an old --env-file of a multi-line .env value) must not eat the lines after it."""
    src = tmp_path / "capture.env"
    src.write_text('AIMARKET_NOTE="unclosed\nAIMARKET_SELLS_FOR=https://atlas.modelmarket.dev\n')
    result = _run(["--literal", "hub", str(src), str(tmp_path / "hub.env")])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "hub.env").read_text() == src.read_text()


def test_unparseable_lines_are_named_by_number_never_by_content(tmp_path):
    src = tmp_path / "source.env"
    src.write_text("AIFACTORY_OK=1\nthis-is-a-secret-without-a-name\nAIFACTORY_Q=\"unterminated\n")
    result = _run(["factory", str(src), str(tmp_path / "factory.env")])
    assert result.returncode != 0
    assert "line 2" in result.stderr and "line 3" in result.stderr
    assert "this-is-a-secret" not in result.stderr + result.stdout


def test_dropped_names_are_printed_without_values(tmp_path):
    src = tmp_path / "source.env"
    src.write_text("AIMARKET_ADMIN_TOKEN=fake-admin-value\nAIFACTORY_PROD=1\n")
    result = _run(["factory", str(src), str(tmp_path / "factory.env")])
    assert result.returncode == 0, result.stderr
    assert "AIMARKET_ADMIN_TOKEN" in result.stdout + result.stderr
    assert "fake-admin-value" not in result.stdout + result.stderr


def test_a_missing_source_refuses_instead_of_writing_an_empty_file(tmp_path):
    result = _run(["stack", str(tmp_path / "absent.env"), str(tmp_path / "env")])
    assert result.returncode != 0
    assert not (tmp_path / "env").exists()


# ── Compose: every generated file is written by one step, and required ────────────────
def _generated_env_files():
    """{compose file: [(service, env_file path)]} for every env_file under deploy/env/."""
    found = {}
    for name in sorted({p.name for p in ROOT.glob("docker-compose*.yml")}) + ["atlas/docker-compose.yml"]:
        base = (ROOT / name).parent
        for svc_name, svc in (_compose(name).get("services") or {}).items():
            entries = svc.get("env_file") or []
            entries = [entries] if isinstance(entries, (str, dict)) else entries
            for entry in entries:
                path = entry if isinstance(entry, str) else entry.get("path", "")
                resolved = (base / path).resolve()
                if ROOT / "deploy" / "env" in resolved.parents:
                    found.setdefault(name, []).append((svc_name, entry, resolved))
    return found


def test_generated_env_files_are_required():
    """`required: false` turned a missing file into a container with no settings at all."""
    found = _generated_env_files()
    assert found, "no compose file reads a generated env file any more — update this test"
    optional = [f"{name}: {svc}" for name, rows in found.items() for svc, entry, _ in rows
                if isinstance(entry, dict) and entry.get("required", True) is not True]
    assert not optional, f"generated env files marked optional: {optional}"


def test_the_stack_step_writes_every_root_compose_env_file(tmp_path):
    src = tmp_path / ".env"
    src.write_text("AIFACTORY_PROD=1\nGF_SMTP_ENABLED=true\nALIEN_API_TOKEN=fake\n")
    result = _run(["stack", str(src), str(tmp_path / "env")])
    assert result.returncode == 0, result.stderr
    wanted = {resolved.name for name, rows in _generated_env_files().items()
              if not name.startswith("atlas/") for _, _, resolved in rows}
    written = {p.name for p in (tmp_path / "env").iterdir()}
    assert wanted <= written, f"compose reads {sorted(wanted - written)} but `stack` never writes them"
    assert "GF_SMTP_ENABLED=true" in (tmp_path / "env" / "grafana.env").read_text()
    assert "AIFACTORY_PROD=1" in (tmp_path / "env" / "factory.env").read_text()


def test_core_tier_monitor_no_longer_takes_the_whole_env():
    for name in ("docker-compose.core.yml", "docker-compose.everything.yml"):
        monitor = _compose(name)["services"]["alien-monitor"]
        paths = [e if isinstance(e, str) else e.get("path") for e in monitor.get("env_file") or []]
        assert ".env" not in [Path(p).name for p in paths], f"{name}: alien-monitor still reads .env whole"


# ── Build context: generated secrets never enter an image ──────────────────────────────
def _dockerignore_excludes(rel: str) -> bool:
    """moby's rule: the last matching pattern wins, and a path is excluded when it or any
    parent directory matches."""
    patterns = []
    for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        patterns.append((negate, line.lstrip("!").strip("/")))
    parts = rel.split("/")
    candidates = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    excluded = False
    for negate, pattern in patterns:
        rx = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
        if any(re.fullmatch(rx, c) for c in candidates):
            excluded = not negate
    return excluded


@pytest.mark.parametrize("path", ["deploy/env/factory.env", "deploy/env/frontend.env", "deploy/env/hub.env",
                                  "deploy/env/atlas.env", "deploy/env/grafana.env", "deploy/env/alien-monitor.env",
                                  "deploy/hub-payment.env", "deploy/hub-zk.env"])
def test_generated_env_files_never_enter_a_build_context(path):
    assert _dockerignore_excludes(".env"), "the matcher itself is broken"
    assert not _dockerignore_excludes("deploy/nginx/atlas.modelmarket.dev.conf"), "the matcher itself is broken"
    assert _dockerignore_excludes(path), f"{path} would be sent to `docker build` and baked by COPY . ."


# ── Every entry point writes the files before it starts anything ───────────────────────
ENTRY_POINTS = {
    # file: regex for the compose invocations that need the generated files
    "scripts/deploy.sh": r'"\$\{COMPOSE_FILES\[@\]\}" (?:build|up)\b',
    "scripts/run_prod_compose.sh": r'\$COMPOSE "\$\{COMPOSE_FILES\[@\]\}" up\b',
    "scripts/deploy_observability.sh": r'docker compose "\$\{COMPOSE_FILES\[@\]\}" up\b',
    "scripts/deploy_atlas.sh": r'docker compose -f "\$compose"[^\n]* up\b',
    ".gitea/workflows/deploy.yml": r'docker compose "\$\{COMPOSE_FILES\[@\]\}" (?:build|up)\b',
    "start.sh": r'"\$\{COMPOSE\[@\]\}" "\$\{UP\[@\]\}"',
    "run-compose.sh": r'\$COMPOSE "\$\{COMPOSE_FILES\[@\]\}" up\b',
    "scripts/everything.sh": r'"\$\{COMPOSE\[@\]\}" (?:"\$\{UP\[@\]\}"|config|build)',
    "scripts/run_factory_demo_reset.sh": r'\$COMPOSE (?:build|up)\b',
    "scripts/verify_storefront_sandbox.sh": r'(?m)^\$\{DC\} up\b',
    "scripts/switch_llm_profile.sh": r'docker compose --env-file \.\./\.env up\b',
}


@pytest.mark.parametrize("path,up", sorted(ENTRY_POINTS.items()), ids=sorted(ENTRY_POINTS))
def test_every_entry_point_generates_before_compose_starts(path, up):
    text = (ROOT / path).read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(up, text)]
    assert starts, f"{path}: no compose start found — the pattern here is stale"
    generate = [m.start() for m in re.finditer(r"scripts/security/service_env\.py\"? (?:stack|atlas)\b", text)]
    late = [text.count("\n", 0, s) + 1 for s in starts if not any(g < s for g in generate)]
    assert not late, f"{path}: compose starts on line(s) {late} before service_env.py writes its env files"


def _shim(bindir: Path, name: str, body: str):
    path = bindir / name
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)


def test_run_prod_compose_writes_fresh_env_files_before_up(tmp_path):
    """Behaviour, not text: compose must find current files at the moment it starts."""
    tree = tmp_path / "tree"
    (tree / "scripts" / "security").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "run_prod_compose.sh", tree / "scripts")
    shutil.copy(SECURITY / "service_env.py", tree / "scripts" / "security")
    (tree / ".env").write_text("POSTGRES_PASSWORD=fake-pg\nREDIS_PASSWORD=fake-redis\n"
                               "GRAFANA_ADMIN_PASSWORD=fake-gf\nDEEPSEEK_API_KEY=fake-new\nAIFACTORY_PROD=1\n")
    # A file left from an earlier deploy, holding a key that has since been rotated.
    (tree / "deploy" / "env").mkdir(parents=True)
    (tree / "deploy" / "env" / "factory.env").write_text("DEEPSEEK_API_KEY=fake-rotated-old\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "compose.log"
    _shim(bindir, "docker", f"""
if [[ "$1 $2" == "compose version" ]]; then exit 0; fi
if [[ " $* " == *" up "* ]]; then
  for f in factory frontend grafana; do
    [[ -f deploy/env/$f.env ]] || {{ echo "missing $f.env" >> "{log}"; exit 9; }}
  done
  cp deploy/env/factory.env "{tmp_path}/factory-at-up.env"
  echo up >> "{log}"
fi
""")
    _shim(bindir, "python3", f'exec "{sys.executable}" "$@"\n')
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    result = subprocess.run(["bash", str(tree / "scripts" / "run_prod_compose.sh"), "--build"],
                            capture_output=True, text=True, cwd=tree, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert log.read_text().split() == ["up"]
    at_up = (tmp_path / "factory-at-up.env").read_text()
    assert "DEEPSEEK_API_KEY=fake-new" in at_up and "fake-rotated-old" not in at_up


def test_atlas_remote_deploy_ships_the_generator(tmp_path):
    """--remote rsyncs only atlas/ and a few files; the host must still be able to cut
    atlas.env, or the deploy there starts ATLAS with no operator token and no LLM key."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "remote.log"
    for tool in ("ssh", "scp", "rsync"):
        _shim(bindir, tool, f'echo "{tool} $*" >> "{log}"; cat >/dev/null 2>&1 || true\n')
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    result = subprocess.run(["bash", str(ROOT / "scripts" / "deploy_atlas.sh"), "--remote", "root@host.invalid", "--no-tls"],
                            capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "scripts/security/service_env.py" in log.read_text()


# ── deploy_hub_rebuild.sh: the capture keeps what the hub reads, and says what it drops ─
def _rebuild_until_build(tmp_path, live_env, *args):
    script = (ROOT / "scripts" / "deploy_hub_rebuild.sh").read_text(encoding="utf-8")
    cut = script.index("# ── 2. Build")
    head = tmp_path / "rebuild_head.sh"
    head.write_text(script[:cut])
    build = tmp_path / "build"
    (build / "scripts" / "security").mkdir(parents=True)
    shutil.copy(SECURITY / "service_env.py", build / "scripts" / "security")
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (tmp_path / "live.json").write_text(json.dumps(live_env))
    _shim(bindir, "docker", f"""
if [[ "$1" == inspect && "$*" == *"json .Config.Env"* ]]; then cat "{tmp_path}/live.json"; exit 0; fi
if [[ "$1" == inspect ]]; then exit 0; fi
exit 1
""")
    _shim(bindir, "python3", f'exec "{sys.executable}" "$@"\n')
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path),
           "AIMARKET_HUB_BUILD_DIR": str(build), "AIMARKET_HUB_ENV_CAPTURE": str(tmp_path / "capture.env")}
    result = subprocess.run(["bash", str(head), *args], capture_output=True, text=True, env=env, cwd=tmp_path)
    return result, tmp_path / "capture.env", build / "deploy" / "hub-payment.env"


LIVE_HUB_ENV = [
    "PATH=/usr/local/bin", "AIFACTORY_PROD=1", "AIFACTORY_CRYPTO_ENABLED=1", "AIFACTORY_PAYMENT_VERIFY_STUB=0",
    "AIFACTORY_PAYMENT_TESTNET=0", "AIMARKET_PAYMENT_RECIPIENT=0x" + "12" * 20,
    "AIMARKET_SELLS_FOR=https://atlas.modelmarket.dev", "AIFACTORY_PAYMENT_MIN_CONFIRMATIONS=6",
    "AIFACTORY_PAYMENT_RPC_BASE=https://base.fake-provider.invalid/k", "BASE_RPC_URL=https://base2.fake-provider.invalid",
    "METIS_URL=https://metis.fake.invalid", "METIS_API_KEY=fake-metis", "DATABASE_URL=postgresql://fake@db/hub",
    # Leftovers from a deploy that handed the hub the whole shared .env.
    "STRIPE_SECRET_KEY=fake-stripe-value", "LOTTERY_AGENT_TOKEN=fake-lottery-value",
]


def test_rebuild_keeps_the_payment_settings_the_hub_reads(tmp_path):
    result, capture, mirror = _rebuild_until_build(tmp_path, LIVE_HUB_ENV, "--allow-drop")
    assert result.returncode == 0, result.stdout + result.stderr
    kept = {line.split("=", 1)[0] for line in capture.read_text().splitlines()}
    assert {"AIFACTORY_PAYMENT_MIN_CONFIRMATIONS", "AIFACTORY_PAYMENT_RPC_BASE", "BASE_RPC_URL",
            "METIS_URL", "METIS_API_KEY", "DATABASE_URL"} <= kept
    assert not {"STRIPE_SECRET_KEY", "LOTTERY_AGENT_TOKEN", "PATH"} & kept
    mirrored = mirror.read_text()
    assert "AIFACTORY_PAYMENT_MIN_CONFIRMATIONS=6" in mirrored and "AIFACTORY_PAYMENT_RPC_BASE=" in mirrored
    assert "fake-stripe-value" not in result.stdout + result.stderr


def test_rebuild_names_what_it_would_drop_and_stops(tmp_path):
    result, capture, mirror = _rebuild_until_build(tmp_path, LIVE_HUB_ENV)
    assert result.returncode != 0
    out = result.stdout + result.stderr
    assert "STRIPE_SECRET_KEY" in out and "LOTTERY_AGENT_TOKEN" in out and "--allow-drop" in out
    assert "fake-stripe-value" not in out and "fake-lottery-value" not in out
    assert not mirror.exists(), "the payment mirror was rewritten by a rollout that stopped"


def test_rebuild_proceeds_silently_when_nothing_is_dropped(tmp_path):
    clean = [e for e in LIVE_HUB_ENV if not e.startswith(("STRIPE_", "LOTTERY_"))]
    result, capture, _ = _rebuild_until_build(tmp_path, clean)
    assert result.returncode == 0, result.stdout + result.stderr
