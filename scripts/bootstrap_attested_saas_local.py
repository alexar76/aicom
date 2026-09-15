#!/usr/bin/env python3
"""Create a private local Attested SaaS deployment env without printing secrets.

The helper issues a dedicated KOVA service key through the local admin API,
generates independent SaaS secrets, and writes the ignored .env.attested-saas
file atomically with mode 0600. It never reads credentials from containers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def require_secret(values: dict[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if len(value) < 24:
        raise RuntimeError(f"{name} is missing or too short in the existing Hub env")
    return value


def issue_kova_key(admin_url: str, admin_token: str) -> tuple[str, str]:
    body = json.dumps({"label": "attested-saas-local", "plan": "business"}).encode()
    request = urllib.request.Request(
        admin_url.rstrip("/") + "/v1/keys",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            value = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", "replace")
        raise RuntimeError(f"KOVA key issue failed with HTTP {exc.code}: {detail}") from exc
    api_key = str(value.get("api_key", ""))
    key_prefix = str(value.get("key_prefix") or api_key[:18])
    if not api_key.startswith("kova_live_") or len(api_key) < 32:
        raise RuntimeError("KOVA returned an invalid service key")
    return api_key, key_prefix


def write_private_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            for key, value in values.items():
                if "\n" in value or "\r" in value:
                    raise RuntimeError(f"newline is not allowed in {key}")
                handle.write(f"{key}={value}\n")
        os.replace(temporary, path)
        path.chmod(0o600)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--kova-admin-url", default="http://127.0.0.1:8789")
    parser.add_argument("--kova-container-url", default="http://host.docker.internal:8789")
    parser.add_argument("--public-origin", default="http://localhost:9401")
    parser.add_argument("--output", type=Path, default=ROOT / ".env.attested-saas")
    parser.add_argument("--rotate", action="store_true", help="replace existing service secrets")
    args = parser.parse_args()

    if not EVM_ADDRESS.fullmatch(args.recipient):
        raise SystemExit("recipient must be a 0x address with 40 hexadecimal characters")

    hub = read_env(ROOT / "attested/attested-memory-hub/.env")
    kova = read_env(ROOT / "independent/kova-gateway/.env")
    root = read_env(ROOT / ".env")
    admin_token = require_secret(kova, "KOVA_ADMIN_TOKEN")
    memory_key = require_secret(hub, "MEMORY_MARKET_API_KEY")
    team_secret = hub.get("SAAS_TEAM_AUTH_SECRET") or root.get("SAAS_TEAM_AUTH_SECRET", "")
    if len(team_secret) < 24:
        raise RuntimeError("SAAS_TEAM_AUTH_SECRET is missing or too short")

    existing = read_env(args.output)
    kova_key = existing.get("KOVA_API_KEY", "") if not args.rotate else ""
    if kova_key.startswith("kova_live_") and len(kova_key) >= 32:
        key_prefix = kova_key[:18]
    else:
        kova_key, key_prefix = issue_kova_key(args.kova_admin_url, admin_token)

    def deployment_secret(name: str) -> str:
        saved = existing.get(name, "") if not args.rotate else ""
        return saved if len(saved) >= 32 else secrets.token_urlsafe(48)

    postgres_password = existing.get("SAAS_POSTGRES_PASSWORD", "") if not args.rotate else ""
    if len(postgres_password) < 32:
        postgres_password = secrets.token_hex(32)
    deployment = {
        "AIFACTORY_PROD": "0",
        "SAAS_POSTGRES_USER": "aicom_saas",
        "SAAS_POSTGRES_PASSWORD": postgres_password,
        "SAAS_POSTGRES_DB": "saas",
        "SAAS_GATEWAY_API_KEY": deployment_secret("SAAS_GATEWAY_API_KEY"),
        "SAAS_EDGE_TOKEN": deployment_secret("SAAS_EDGE_TOKEN"),
        "SAAS_KEY_DERIVATION_SECRET": deployment_secret("SAAS_KEY_DERIVATION_SECRET"),
        "SAAS_RECONCILE_SECONDS": "15",
        "SAAS_KEY_REVEAL_HOURS": "48",
        "KOVA_URL": args.kova_container_url,
        "KOVA_API_KEY": kova_key,
        "SAAS_PAYMENT_RECIPIENT": args.recipient,
        "SAAS_TEAM_AUTH_SECRET": team_secret,
        "SAAS_PUBLIC_ORIGIN": args.public_origin,
        "MEMORY_MARKET_URL": "http://memory-market:8810",
        "MEMORY_MARKET_API_KEY": memory_key,
        "ATTESTED_HUB_NETWORK": "attested-memory-hub_default",
    }
    write_private_env(args.output, deployment)
    print(f"wrote {args.output} (0600)")
    print(f"recipient={args.recipient}")
    print(f"kova_service_key_prefix={key_prefix}")
    print("mode=local (AIFACTORY_PROD=0; production requires HTTPS public origin)")


if __name__ == "__main__":
    main()
