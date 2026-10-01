"""Bootstrap secrets vault from flat files and export LLM keys to the environment."""

from __future__ import annotations

from security.secret_resolver import export_llm_keys_to_env, sync_file_secrets_into_fernet_vault


def bootstrap_secrets() -> None:
    """Called from entrypoint after load_docker_secret_env.sh."""
    sync_file_secrets_into_fernet_vault()
    export_llm_keys_to_env()


if __name__ == "__main__":
    bootstrap_secrets()
    n = export_llm_keys_to_env()
    print(f"bootstrap_secrets: exported {n} LLM key(s) to environment")
