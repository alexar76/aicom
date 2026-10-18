#!/usr/bin/env python3
"""Isolated local workshop launcher. No federation announcements or payments."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".runtime"


def private_json(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    path.chmod(0o600)


def environment():
    if not (STATE / "secrets.json").exists():
        raise SystemExit("Run: python run.py init")
    keys = json.loads((STATE / "secrets.json").read_text())
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AIMARKET_", "AIFACTORY_", "N8N_", "DB_"))
           and k not in ("DATABASE_URL", "WEBHOOK_URL")}
    env.update({
        "AIMARKET_DB_PATH": str(STATE / "hub.db"),
        "AIMARKET_SIGNING_KEY_PATH": str(STATE / "hub_key"),
        "AIMARKET_HUB_URL": "http://127.0.0.1:19083",
        "AIMARKET_HUB_NAME": "Workshop Store — local demo",
        "AIMARKET_ADMIN_TOKEN": keys["admin"],
        "AIMARKET_CAPABILITY_TOKEN": keys["hub_to_adapter"],
        "AIMARKET_INVOKE_HOST_GATEWAY": "127.0.0.1",
        "AIMARKET_ALLOW_LOCAL_PUBLISH": "1",
        "AIMARKET_AUTO_CRAWL": "0",
        "AIMARKET_ORACLE_FAMILY_URL": "off",
        "AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG": "1",
        "AIMARKET_CREDITS_ENABLED": "1",
        "AIMARKET_CREDITS_FREE_GRANT_USD": "0",
        "AIMARKET_PQC": "1",
        "WORKSHOP_WEBHOOK_TOKEN": keys["webhook"],
        "N8N_USER_FOLDER": str(STATE / "n8n"),
        "N8N_ENCRYPTION_KEY": keys["n8n_encryption"],
        "N8N_HOST": "127.0.0.1", "N8N_LISTEN_ADDRESS": "127.0.0.1",
        "N8N_PORT": "15678", "N8N_PROTOCOL": "http",
        "N8N_SECURE_COOKIE": "false",  # loopback HTTP lab only
        "N8N_DIAGNOSTICS_ENABLED": "false", "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
        "N8N_TEMPLATES_ENABLED": "false", "N8N_PERSONALIZATION_ENABLED": "false",
        "N8N_WEBHOOK_URL": "http://127.0.0.1:15678/",
        "EXECUTIONS_DATA_SAVE_ON_SUCCESS": "none", "EXECUTIONS_DATA_SAVE_ON_ERROR": "none",
    })
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "n8n-import", "n8n", "adapter", "hub", "check"])
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.command == "init":
        STATE.mkdir(mode=0o700, exist_ok=True)
        STATE.chmod(0o700)
        if not (STATE / "secrets.json").exists():
            private_json(STATE / "secrets.json", {k: secrets.token_urlsafe(32) for k in
                         ("admin", "hub_to_adapter", "webhook", "n8n_encryption")})
    env = environment()
    os.environ.clear()
    os.environ.update(env)
    # Hub modules may initialise auxiliary relative-path databases during import.
    # Keep all such side effects in the ignored, private workshop state directory.
    os.chdir(STATE)
    if args.command == "init":
        from aimarket_hub.cli import main as cli
        from aimarket_hub.signing import Signer
        subprocess.run([sys.executable, str(ROOT / "build_workflow.py")], check=True)
        cli(["quickstart", "--name", env["AIMARKET_HUB_NAME"], "--url", env["AIMARKET_HUB_URL"],
             "--no-sample", "--no-buyer"])
        pubkey = Signer(STATE / "provider_key", pqc=False).public_key_b64
        code = cli(["add", "store.order_check@v1", "--product", "workshop-store",
                    "--name", "Read-only order check (synthetic catalogue)",
                    "--description", "Check a demo cart against synthetic stock and prices. No reservation or purchase. USD minor units; excludes tax/shipping.",
                    "--url", "http://127.0.0.1:13456/invoke", "--price", "0",
                    "--provider-pubkey", pubkey, "--input-schema", "@" + str(ROOT / "input-schema.json")])
        if code:
            raise SystemExit(code)
        private_json(STATE / "credentials.json", [{
            "id": "aimarketWorkshopWebhook", "name": "Workshop webhook secret",
            "type": "httpHeaderAuth", "data": {"name": "X-Workshop-Key", "value": env["WORKSHOP_WEBHOOK_TOKEN"]}
        }])
        print("Initialised local workshop. Secrets stay in .runtime/; do not share it.")
    elif args.command in ("n8n", "n8n-import"):
        binary = shutil.which("n8n")
        if not binary:
            raise SystemExit("n8n not found. Install n8n@2.43.7 in an isolated directory and add its node_modules/.bin to PATH.")
        if args.command == "n8n-import":
            subprocess.run([binary, "import:credentials", "--input", str(STATE / "credentials.json")], check=True)
            subprocess.run([binary, "import:workflow", "--input", str(ROOT / "workflow.json")], check=True)
            subprocess.run([binary, "publish:workflow", "--id", "aimarketOrderCheckWorkshop"], check=True)
            print("Imported and published. Restart the workshop n8n process after re-importing.")
        else:
            os.execv(binary, [binary, "start"])
    elif args.command == "adapter":
        import uvicorn
        from adapter import create_app
        uvicorn.run(create_app(), host="127.0.0.1", port=13456, access_log=False)
    elif args.command == "hub":
        # Auxiliary Hub databases/keys with relative defaults also stay in the lab state.
        os.chdir(STATE)
        import uvicorn
        from aimarket_hub.api import create_app
        from aimarket_hub.config import HubConfig
        config = HubConfig()
        config.seed_list = []
        config.auto_crawl = False
        uvicorn.run(create_app(config=config), host="127.0.0.1", port=19083, access_log=False)
    else:
        from check import check
        check()


if __name__ == "__main__":
    main()
