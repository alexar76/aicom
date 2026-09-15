"""Environment scrubbing for child processes that run UNTRUSTED generated code.

The factory generates product code with an LLM and then *runs* it: the sandbox
preview pip-installs a product's ``requirements.txt`` (build hooks execute) and
imports its modules under uvicorn, and the pipeline worker executes the product's
runtime test commands. ``docs/sandbox-trust-model.md`` classifies that code as
untrusted, and the per-sandbox venv isolates **packages** — it never isolated
**privilege**.

Both call sites used to hand the child ``os.environ`` wholesale, which is the
factory's own credential set: LLM provider keys, the JWT signing secret (mint an
admin token), the hub admin token, Postgres/Redis credentials, the publish tokens
(Vercel, GitHub), and ``DOCKER_HOST`` plus client certs (reach the daemon, escape
the container). One prompt-shaped product brief was enough to reach it.

The deny-list is deliberately broad and matches on substrings: a provider key
added to ``.env`` next month must be excluded **by default**, never opted in by
whoever remembers to edit this file.
"""

from __future__ import annotations

from typing import Iterable, Mapping

#: Exact keys dropped so a caller's own sandbox default applies instead of the
#: factory's live value. Callers that re-set these (``setdefault``) get the
#: sandbox value; callers that do not simply see the variable unset.
DROP_EXACT: frozenset[str] = frozenset(
    {
        "DATABASE_URL",            # else generated code talks to the FACTORY database
        "PIPELINE_DATABASE_URL",
        "REDIS_URL",
        "AIFACTORY_REDIS_URL",
        "SECRET_KEY",
        "SANDBOX_DEMO_PASSWORD",
        "DOCKER_HOST",             # daemon access == container escape
        "DOCKER_CERT_PATH",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CONFIG",
        "SSH_AUTH_SOCK",
        "GIT_ASKPASS",
        "GIT_CONFIG_GLOBAL",
        "AIFACTORY_ADMIN_PASSWORD",
        "AIFACTORY_DEV_BOOTSTRAP_PASSWORD",
    }
)

#: Substring match against the upper-cased key.
DROP_SUBSTRINGS: tuple[str, ...] = (
    "SECRET", "TOKEN", "PASSWORD", "PASSWD", "APIKEY", "API_KEY", "_KEY", "KEYFILE",
    "PRIVKEY", "PRIVATE", "CREDENTIAL", "MNEMONIC", "SEED_PHRASE", "SIGNING",
    "WEBHOOK", "SENTRY_DSN", "AWS_", "VERCEL", "GITHUB", "GH_PAT", "GITEA",
    "OPENROUTER", "DEEPSEEK", "ANTHROPIC", "OPENAI", "OLLAMA_KEY", "TELEGRAM",
    "DISCORD", "SMTP", "TWILIO", "STRIPE", "INFURA", "ALCHEMY", "RPC_URL",
)


def is_sensitive(key: str) -> bool:
    """Would this environment variable leak a credential to untrusted code?"""
    upper = key.upper()
    if upper in DROP_EXACT:
        return True
    return any(frag in upper for frag in DROP_SUBSTRINGS)


def scrub_child_env(
    source: Mapping[str, str],
    *,
    keep: Iterable[str] = (),
) -> dict[str, str]:
    """Copy of ``source`` without anything untrusted code has no business seeing.

    ``keep`` re-admits specific keys by exact name, for the rare child that needs
    one (pass it explicitly at the call site so the exception is reviewable).
    """
    keep_set = {k for k in keep}
    return {
        key: value
        for key, value in source.items()
        if key in keep_set or not is_sensitive(key)
    }
