#!/usr/bin/env python3
"""Filter shared deployment settings into service-scoped env files.

    service_env.py atlas .env deploy/env/atlas.env    one service
    service_env.py stack .env deploy/env              every file the root compose files read

Run it before every `docker compose up`: the compose files require these files, and a file
left from an earlier deploy still holds whatever .env said back then.
Values remain on the deployment host; output names variables and counts, never values.

Each service gets the namespaces it owns plus the names outside them that its code and
compose files read. tests/test_service_env_scope.py scans the code for those names and
fails when one is missing here, because a dropped setting does not stop a service: it
starts anyway and quietly falls back to a default.
"""
import argparse
import os
import re
from pathlib import Path

# Read by the runtime or by every HTTP client library rather than by our code: the clock, and
# egress through a proxy or a private CA. They reached every service while each took .env whole.
COMMON = {"TZ", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
          "no_proxy", "all_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE"}
# The LLM routers read whichever key the provider YAML names (`api_key_env`), and that file
# is operator-edited, so every provider it may point at is allowed together.
PROVIDER_KEYS = {"DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
                 "GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "TOGETHER_API_KEY"}
# Chain endpoints read by chain_net, which the Factory, the hub and the monitor all run: the
# legacy single-URL names, and AIMARKET_RPC_<CHAIN> / AIMARKET_ADDR_<CHAIN>_<NAME> by prefix.
# Without them payment verification quietly falls back to public RPCs.
CHAIN = {"BASE_RPC_URL", "ETHEREUM_RPC_URL", "ARBITRUM_RPC_URL", "SOLANA_RPC_URL",
         "AIFACTORY_PAYMENT_RPC_BASE", "AIFACTORY_PAYMENT_RPC_ETHEREUM",
         "AIFACTORY_PAYMENT_RPC_ARBITRUM", "AIFACTORY_PAYMENT_RPC_SOLANA",
         "AIMARKET_RPC_COOLDOWN", "AIMARKET_RPC_MAX_COOLDOWN", "AIMARKET_RPC_RETRIES",
         "AIMARKET_RPC_TIMEOUT", "AIMARKET_RPC_USER_AGENT", "AIFACTORY_DEPLOYMENTS_DIR"}
CHAIN_FAMILIES = ("AIMARKET_RPC_", "AIMARKET_ADDR_")

# service: (namespaces it owns, names outside them that it reads)
SCOPES = {
    "factory": (("AIFACTORY_", "PIPELINE_", "AICOM_", "NEXT_PUBLIC_") + CHAIN_FAMILIES, PROVIDER_KEYS | CHAIN | {
        # Its own runtime: entrypoint.sh, uvicorn, the database and queue.
        "SQLITE_PATH", "USE_SQLITE", "DATABASE_URL", "POSTGRES_PASSWORD", "REDIS_PASSWORD", "REDIS_URL",
        "UVICORN_WORKERS", "UVICORN_LOG_LEVEL", "INTERNAL_API_URL", "PROMETHEUS_MULTIPROC_DIR", "NODE_ENV",
        "BACKEND_HEALTH_FAILS_BEFORE_KILL", "BACKEND_HEALTH_PATH", "BACKEND_MAX_RESTARTS",
        "BACKEND_RESTART_WINDOW_SECS", "JWT_SECRET_KEY", "JWT_SECRET_FILE", "CUSTOMER_JWT_SECRET",
        "CUSTOMER_JWT_SECRET_FILE", "ADMIN_USERS_PATH", "GIT_CREDENTIALS_FILE", "VAULT_ADDR", "VAULT_TOKEN",
        "REMEDIATION_HOST", "REMEDIATION_PORT", "PUBLIC_SITE_URL",
        "PUBLIC_METRICS_FETCH_TIMEOUT", "BLOG_CAPTURE_INDEX_RELPATH", "CORPORATE_CHAT_PIPELINE_EVENTS",
        "SANDBOX_DEMO_EMAIL", "SANDBOX_DEMO_PASSWORD",
        "UNI_DATABASE_URL", "UNI_DB_BACKEND", "UNI_SQLITE_PATH", "UNI_USE_POSTGRES",
        # The DinD sidecar (docker-compose.dind.yml).
        "DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
        # Checkout, publishing and notifications.
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "VERCEL_TOKEN", "VERCEL_ORG_ID", "GH_PAT",
        "GITHUB_TOKEN", "RAILWAY_TOKEN", "NETLIFY_AUTH_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "OUTREACH_SMTP_FROM",
        "OUTREACH_SMTP_HOST", "OUTREACH_SMTP_PASSWORD", "OUTREACH_SMTP_PORT", "OUTREACH_SMTP_TO",
        "OUTREACH_SMTP_USER", "OUTREACH_TELEGRAM_BOT_TOKEN", "OUTREACH_TELEGRAM_CHAT_ID",
        "OUTREACH_WEBHOOK_URL", "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "OTEL_SDK_DISABLED",
        "OTEL_SERVICE_NAME", "OTEL_TRACE_URL_TEMPLATE",
        # Ecosystem it calls or links to, and what generated products are deployed with.
        "METIS_URL", "METIS_API_KEY", "HUB_PUBLIC_URL", "ALIEN_MONITOR_PUBLIC_URL", "ATLAS_BASE_URL",
        "ATLAS_PUBLIC_URL", "ATLAS_AGENT_KEY", "SENTINEL_WALLET_KEY", "SENTINEL_DAILY_INVOKE_BUDGET_USD",
        "WALLET_ADDRESS", "WALLET_CHAIN", "X_AIMARKET_SANDBOX_VISITOR", "X_PAYMENT_CHANNEL",
        "X_PAYMENT_CHANNEL_SECRET", "BASE_RPC",
        # Hub and ACEX code the Factory runs in-process: funnel auto-listing into a local hub
        # database, the ACEX IPO/audit ledgers, payment verification through chain_net.
        "ACEX_AI_AUDIT_FEDERATED_SEARCH", "ACEX_AUDIT_BRIDGE_MODE", "ACEX_AUDIT_DB_PATH",
        "ACEX_AUDIT_FEE_BPS", "ACEX_AUDIT_POOL_ADDRESS", "ACEX_AUTO_IPO", "ACEX_DEFAULT_MAX_SUPPLY",
        "ACEX_HUB_LISTINGS_URL", "ACEX_HUB_SEARCH_URL", "ACEX_IPO_DB_PATH", "ACEX_MAX_STREAM_CLIENTS",
        "ACEX_MIN_AUDIT_SCORE_BPS", "ACEX_MIN_LISTING_REVENUE_USD", "ACEX_MOMUS_FINDINGS_URL",
        "ACEX_REQUIRE_AI_AUDIT", "ACEX_REVENUE_SHARE_BPS", "ACEX_SNAPSHOT_BUILD_TIMEOUT_SEC",
        "ACEX_SNAPSHOT_STALE_SEC", "ACEX_SNAPSHOT_TTL_SEC", "ACEX_TREASURY_HOLDER",
        "AIMARKET_ACEX_AUDIT_DATABASE_URL", "AIMARKET_ACEX_IPO_DATABASE_URL", "AIMARKET_ALLOW_DEMO_CREDIT",
        "AIMARKET_ALLOW_LOCAL_PUBLISH", "AIMARKET_AUTO_CRAWL", "AIMARKET_BASE_URL",
        "AIMARKET_CAP_DESCRIPTIONS_PATH", "AIMARKET_CATALOG_MAX_STALE_S", "AIMARKET_CHAIN",
        "AIMARKET_CHAIN_CLUSTER", "AIMARKET_CHAIN_ID", "AIMARKET_CHAIN_KIND", "AIMARKET_CHAIN_REALM",
        "AIMARKET_CHAIN_SYMBOL", "AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER", "AIMARKET_CHANNEL_CACHE",
        "AIMARKET_CHANNEL_DEPOSIT_USD", "AIMARKET_CHARITY_ENABLED", "AIMARKET_CHARITY_INTERVAL_HOURS",
        "AIMARKET_CHARITY_LOTTERY_ADDRESS", "AIMARKET_CHARITY_LOTTERY_CHAIN_ID", "AIMARKET_CHARITY_TITHE_BPS",
        "AIMARKET_CRAWL_INITIAL_DELAY_S", "AIMARKET_CRAWL_INTERVAL_S", "AIMARKET_CRAWL_REFRESH_MAX",
        "AIMARKET_DB_PATH", "AIMARKET_DEPOSIT_CLAIMS_DIR", "AIMARKET_DEPOSIT_TX",
        "AIMARKET_DISCOVER_MAX_PER_IP_PER_MIN",
        "AIMARKET_ECOSYSTEM_LINKS", "AIMARKET_ESCROW_CHANNEL", "AIMARKET_ESCROW_CONTRACT",
        "AIMARKET_ESCROW_EVM_ADDRESS", "AIMARKET_ESCROW_HUB_ADDRESS", "AIMARKET_ESCROW_SOLANA_PROGRAM_ID",
        "AIMARKET_FACTORY_SEED_USD", "AIMARKET_FEDERATION_ASSAY", "AIMARKET_FEDERATION_ASSAY_AUTO_TRUST",
        "AIMARKET_FEDERATION_ASSAY_LLM", "AIMARKET_FEDERATION_ASSAY_REQUIRE",
        "AIMARKET_FEDERATION_ASSAY_RETRY_S", "AIMARKET_FEDERATION_ASSAY_SANDBOX",
        "AIMARKET_FEDERATION_ASSAY_TIMEOUT_S", "AIMARKET_FEDERATION_ASSAY_TTL_S",
        "AIMARKET_FEDERATION_AUTO_ADMIT", "AIMARKET_FEDERATION_GOSSIP_MAX_OBSERVED",
        "AIMARKET_FEDERATION_JUDGE_MODEL", "AIMARKET_FEDERATION_JUDGE_REQUIRED",
        "AIMARKET_FEDERATION_JUDGE_URL", "AIMARKET_FEDERATION_OPEN", "AIMARKET_FEDERATION_OPEN_MAX_PENDING",
        "AIMARKET_FEDERATION_PREVIEW_CAPS", "AIMARKET_FEDERATION_PREVIEW_MAX_CAPS", "AIMARKET_HUB_BOND_CHAIN",
        "AIMARKET_HUB_BOND_ENFORCED", "AIMARKET_HUB_BOND_TOKEN", "AIMARKET_HUB_BOND_USD", "AIMARKET_HUB_NAME",
        "AIMARKET_HUB_PUBLIC_URL", "AIMARKET_HUB_URL", "AIMARKET_INVOKE_ATLAS", "AIMARKET_INVOKE_HOST_GATEWAY",
        "AIMARKET_INVOKE_MAX_PER_CUSTOMER_PER_MIN", "AIMARKET_INVOKE_MAX_PER_IP_PER_MIN",
        "AIMARKET_MANIFEST_MAX_AGE_S", "AIMARKET_MAX_CRAWL_DEPTH", "AIMARKET_MIN_TRUST_SCORE",
        "AIMARKET_NETWORK", "AIMARKET_NONCE_WAIT_S", "AIMARKET_PAYMENT_CHAIN", "AIMARKET_PAYMENT_CHAINS",
        "AIMARKET_PAYMENT_CHANNEL", "AIMARKET_PAYMENT_CHANNEL_SECRET", "AIMARKET_PAYMENT_RECIPIENT",
        "AIMARKET_PAYMENT_TOKEN", "AIMARKET_PAYMENT_TOKENS", "AIMARKET_PQC", "AIMARKET_PQC_REQUIRE",
        "AIMARKET_PQ_RATCHET", "AIMARKET_PRODUCT_ID", "AIMARKET_PUBLISHER_SHARE_BPS",
        "AIMARKET_REQUEST_TIMEOUT_S", "AIMARKET_ROUTING_FEE_BPS", "AIMARKET_RPC_URL",
        "AIMARKET_SANDBOX_STUB_INVOKE", "AIMARKET_SANDBOX_VISITOR", "AIMARKET_SCHEMA_DIR",
        "AIMARKET_SEEDS_FILE", "AIMARKET_SEED_LIST", "AIMARKET_SEED_PUBKEYS", "AIMARKET_SELLS_FOR",
        "AIMARKET_SIGNING_KEY_PATH", "AIMARKET_SLASH_ACCEPT_WEAK", "AIMARKET_SOURCE_HUB",
        "AIMARKET_SOURCE_URL", "AIMARKET_SQLITE_BUSY_TIMEOUT_S", "AIMARKET_SUPPLY_SECURITY_RELAXED",
        "AIMARKET_TESTNET", "AIMARKET_TOKEN", "AIMARKET_UNI_CHAIN_ID", "AIMARKET_UNI_FEDERATION_HOSTS",
        "AIMARKET_USDC", "AIMARKET_WALLET_ADDRESS", "AIMARKET_WALLET_KEY", "AIMARKET_WIDGET_FEDERATE_SEARCH",
        "AIMARKET_ZK_BACKEND", "AIMARKET_ZK_SIMULATED", "AIMARKET_ZK_SNARKJS", "AIMARKET_ZK_VERIFIER_SOL",
        "AIMARKET_ZK_VKEY", "AIMARKET_ZK_VKEY_JSON", "AIMARKET_ZK_WASM", "AIMARKET_ZK_ZKEY",
    }),
    # The split Next.js server (docker-compose.prod.yml): its security headers and API origin.
    "frontend": (("NEXT_PUBLIC_",), {
        "INTERNAL_API_URL", "AICOM_BACKEND_INTERNAL_URL", "AICOM_ROLE", "AIFACTORY_SERVER_API_SOURCE",
        "AIFACTORY_FRONTEND_CSP", "AIFACTORY_ENABLE_DEFAULT_CSP", "AIFACTORY_ENABLE_HSTS",
        "AIFACTORY_HSTS_PRELOAD", "AIFACTORY_DATA_ROOT", "NODE_ENV",
    }),
    "hub": (("AIMARKET_", "ACEX_"), CHAIN | {
        "AIFACTORY_PROD", "AIFACTORY_CRYPTO_ENABLED", "AIFACTORY_PAYMENT_TESTNET",
        "AIFACTORY_PAYMENT_VERIFY_STUB", "AIFACTORY_PAYMENT_MIN_CONFIRMATIONS",
        "AIFACTORY_AI_MARKET_CONTRACT", "AIFACTORY_DATA_ROOT", "AIFACTORY_PUBLIC_URL",
        # Postgres is mandatory for a production hub (api.py refuses SQLite when AIFACTORY_PROD=1).
        "DATABASE_URL", "SQLITE_PATH",
        # Verified settlement and federation assay; the judge falls back to the fleet key.
        "METIS_URL", "METIS_API_KEY", "OPENROUTER_API_KEY", "ARGUS_ORACLE_FAMILY_URL",
    }),
    "atlas": (("ATLAS_",), PROVIDER_KEYS | {
        "AIFACTORY_PROD", "ORACLE_PQC", "ORACLE_PQC_REQUIRE", "ALIEN_LLM_CONFIG",
    }),
    # The core-tier monitor (docker-compose.core.yml): mostly addresses of the satellites it draws.
    "alien-monitor": (("ALIEN_",) + CHAIN_FAMILIES, PROVIDER_KEYS | CHAIN | {
        "AICOM_API_URL", "AICOM_CONTRACTS_EVM_DIR", "AIFACTORY_AI_MARKET_CHAIN", "AIFACTORY_AI_MARKET_CONTRACT",
        "AIFACTORY_CRYPTO_ENABLED", "AIFACTORY_PROD", "AIFACTORY_PRODUCTION", "AIFACTORY_PUBLIC_URL",
        "AIFACTORY_UNI_GRANT_SECRET", "AIFACTORY_URL", "AIMARKET_CHAIN", "AIMARKET_CHAIN_CLUSTER",
        "AIMARKET_CHAIN_ID", "AIMARKET_CHAIN_KIND", "AIMARKET_CHAIN_SYMBOL", "AIMARKET_ESCROW_CONTRACT",
        "AIMARKET_ESCROW_EVM_ADDRESS", "AIMARKET_ESCROW_HUB_ADDRESS", "AIMARKET_ESCROW_SOLANA_PROGRAM_ID",
        "AIMARKET_HUB_URL", "AIMARKET_LOTTERY_CONTRACT", "AIMARKET_LOTTERY_EVM_ADDRESS", "AIMARKET_NETWORK",
        "AIMARKET_NFT_CHAIN", "AIMARKET_NFT_CHAIN_RPC", "AIMARKET_NFT_CONTRACT",
        "AIMARKET_NFT_CONTRACT_ADDRESS", "AIMARKET_PAYMENT_CHAIN", "AIMARKET_PAYMENT_RECIPIENT",
        "AIMARKET_PUBLIC_HUB_URL", "AIMARKET_TESTNET", "ARGUS_HTTP_TOKEN", "ARGUS_PUBLIC_UNI_URL",
        "ARGUS_PUBLIC_URL", "ARGUS_UNI_URL", "ARGUS_URL", "ATLAS_GITHUB_URL", "ATLAS_PUBLIC_URL", "ATLAS_URL",
        "BASANOS_PUBLIC_URL", "BASANOS_URL", "BRIDGES_GITHUB_URL", "BRIDGES_PUBLIC_URL", "BRIDGES_PYPI_URL",
        "BRIDGES_URL", "DIOSCURI_DISCORD_URL", "DIOSCURI_GITHUB_URL", "DIOSCURI_PUBLIC_URL",
        "DIOSCURI_TELEGRAM_BOT_URL", "DIOSCURI_TELEGRAM_CHANNEL_URL", "DIOSCURI_TELEGRAM_URL", "DIOSCURI_URL",
        "DOLOS_LAST_SCAN_PATH", "DOLOS_PUBLIC_URL", "ECO_PUBLIC_BASE", "GAIA_GITHUB_URL", "GAIA_PUBLIC_URL",
        "GAIA_URL", "HELIOS_PUBLIC_URL", "HELIOS_URL", "HELIOS_YOUTUBE_URL", "HEPHAESTUS_PUBLIC_URL",
        "HESTIA_PUBLIC_URL", "HESTIA_URL", "HISTOR_PUBLIC_URL", "HISTOR_URL", "HUB_PUBLIC_URL", "HUB_URL",
        "LOGOS_URL", "LUMEN_URL", "MESH_URL", "METIS_API_KEY", "METIS_GITHUB_URL", "METIS_PUBLIC_URL",
        "METIS_URL", "MOMUS_BOUNTY_SOLANA_ACCOUNT", "MOMUS_BOUNTY_SPLITTER", "MOMUS_GITHUB_URL",
        "MOMUS_PUBLIC_URL", "MOMUS_URL", "NEXT_PUBLIC_SITE_URL", "PROMETHEUS_URL", "PUBLIC_SITE_URL",
        "SKOPOS_GITHUB_URL", "SKOPOS_PUBLIC_URL", "SKOPOS_URL", "SOLANA_DEPLOYER_KEYPAIR", "THEOROS_URL",
        "TREASURY_GITHUB_URL", "TREASURY_PUBLIC_URL", "TREASURY_URL",
    }),
    "grafana": (("GF_",), set()),
}

# Read by code inside the service's image, and still withheld.
DENY = {
    "factory": {
        # aimarket_hub.config builds a whole HubConfig when the Factory imports it for funnel
        # auto-listing, but only a hub admitting peers uses the judge key, and only a hub
        # reselling to peers uses their per-peer billing keys.
        "AIMARKET_FEDERATION_JUDGE_KEY", "AIMARKET_PEER_API_KEYS",
    },
    "hub": {
        # Read only by acex/scripts/pulse_amm_create_pool_plan.py, an offline operator tool
        # that ships in the image because the Dockerfile copies acex/ whole.
        "ACEX_DEPLOYER_KEY",
        # The Factory's product wallet (vercel_fullstack_adapter); the hub never reads it.
        "AIMARKET_WALLET_KEY",
    },
}

# Set by each image (Dockerfile ENV or its base image). Left out so a container rolled onto
# a new image gets that image's values: carrying PATH forward from an older base image is how
# a rebuilt container ends up unable to find python (deploy_hub_rebuild.sh drops the same set).
IMAGE_OWNED = re.compile(r"PATH|HOSTNAME|LANG|GPG_KEY|PYTHON_[A-Z0-9_]+")

# `stack` writes what docker-compose.yml and its overlays read: app and the prod workers,
# the split frontend, grafana, and the core-tier monitor.
STACK = ("factory", "frontend", "grafana", "alien-monitor")
# The hub runs under `docker run --env-file`, which takes each line literally: no quoting,
# so no multi-line values. Everything else is read by compose, which parses dotenv syntax.
DOCKER_ENV_FILE = {"hub"}
KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def allowed(service, key):
    if service not in SCOPES:
        raise ValueError("Unknown service")
    prefixes, names = SCOPES[service]
    if IMAGE_OWNED.fullmatch(key) or key in DENY.get(service, ()):
        return False
    return key in COMMON or key in names or key.startswith(prefixes)


def filtered(service, entries):
    """KEY=VALUE entries with literal values (a container's Config.Env) → the kept ones."""
    # Match the runtime's last-assignment semantics.
    values = {}
    for line in entries:
        key, sep, value = line.partition("=")
        if sep and allowed(service, key):
            if "\n" in value or "\r" in value:
                raise ValueError("Multiline env values cannot be written to an env file")
            values[key] = value
    return [key + "=" + value for key, value in values.items()]


def _closes(text, quote):
    """True when `text` (starting with its opening quote) holds the closing one."""
    i = 1
    while i < len(text):
        if quote == '"' and text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return True
        i += 1
    return False


def parse(text, literal=False):
    """({key: raw value}, [unreadable line numbers]), last assignment winning.

    .env is dotenv syntax, read the way compose reads it: `export`, indentation and spaces
    around `=` are normalised away, and a quoted value — multi-line included — is kept as
    written, so compose reads the output exactly as it would have read .env (and docker,
    for the hub, gets the same text it got from .env before). Splitting into lines first,
    as this used to, cut a multi-line value into an unterminated quote that made compose
    refuse the whole file.

    `literal` is for `docker inspect` output: one KEY=VALUE per line, the value exactly as
    the container holds it. A value there that opens a quote must not swallow the lines
    after it.
    """
    values, bad = {}, []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        number, line = i + 1, lines[i]
        i += 1
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        body = line.lstrip()
        if body.startswith("export "):
            body = body[len("export "):].lstrip()
        key, sep, value = body.partition("=")
        key = key.strip()
        if not sep or not KEY.fullmatch(key):
            bad.append(number)
            continue
        if literal:
            values[key] = value
            continue
        value = value.lstrip()
        if value[:1] in ("'", '"'):
            while not _closes(value, value[0]) and i < len(lines):
                value += "\n" + lines[i]
                i += 1
            if not _closes(value, value[0]):
                bad.append(number)
                continue
        else:
            value = value.rstrip()
        values[key] = value
    return values, bad


def write(service, source, destination, literal=False):
    """Write the service's file; return (kept, dropped) names. Refuses unreadable input."""
    values, bad = parse(source.read_text(encoding="utf-8"), literal)
    if bad:
        # Line numbers only: a line that is not KEY=VALUE may well be a pasted secret.
        raise SystemExit(f"service_env: {source}: cannot read {', '.join(f'line {n}' for n in bad)} "
                         "as KEY=VALUE; fix it so no setting is silently lost")
    kept = {k: v for k, v in values.items() if allowed(service, k)}
    multiline = sorted(k for k, v in kept.items() if "\n" in v)
    if service in DOCKER_ENV_FILE and multiline:
        raise SystemExit(f"service_env: {', '.join(multiline)}: `docker --env-file` cannot carry a "
                         "multi-line value; store it in a file the container reads instead")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("".join(f"{k}={v}\n" for k, v in kept.items()))
    os.replace(tmp, destination)
    return sorted(kept), sorted(set(values) - set(kept))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("service", choices=sorted(SCOPES) + ["stack"])
    ap.add_argument("source", type=Path)
    ap.add_argument("destination", type=Path, help="the env file, or with `stack` its directory")
    ap.add_argument("--literal", action="store_true",
                    help="source is `docker inspect` KEY=VALUE lines, not dotenv syntax")
    args = ap.parse_args()
    if not args.source.is_file():
        # Refuse rather than write nothing: compose would then start the service without its
        # settings, which is the failure these files exist to prevent.
        raise SystemExit(f"service_env: {args.source} not found — refusing to start services without it")
    jobs = ([(s, args.destination / f"{s}.env") for s in STACK] if args.service == "stack"
            else [(args.service, args.destination)])
    for service, destination in jobs:
        kept, dropped = write(service, args.source, destination, args.literal)
        print(f"Wrote {len(kept)} variables for {service}"
              + (f" (left out: {', '.join(dropped)})" if dropped else ""))


if __name__ == "__main__":
    main()
