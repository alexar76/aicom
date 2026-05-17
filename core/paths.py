from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    return Path(os.environ.get("AIFACTORY_DATA_ROOT", "/app/data"))


def resolve_data_root(value: str | Path | None = None) -> Path:
    """Resolve optional caller override to the configured data root."""
    if value is None:
        return data_root()
    return Path(value)


def app_root() -> Path:
    """Application install root (repo root in dev, ``/app`` in Docker)."""
    return Path(os.environ.get("AIFACTORY_APP_ROOT", "/app"))


def venv_python() -> Path:
    return Path(os.environ.get("AIFACTORY_VENV_PYTHON", str(app_root() / "venv" / "bin" / "python")))


def scripts_dir() -> Path:
    return Path(os.environ.get("AIFACTORY_SCRIPTS_DIR", str(app_root() / "scripts")))


def git_repos_dir() -> Path:
    return Path(os.environ.get("AIFACTORY_GIT_REPOS_DIR", str(app_root() / "git-repos")))


def config_dir() -> Path:
    return data_root() / "config"


def secrets_dir() -> Path:
    return data_root() / "secrets"


def arch_data_dir() -> Path:
    return data_root() / "arch"


def sandboxes_dir() -> Path:
    return Path(os.environ.get("AIFACTORY_SANDBOXES_DIR", str(data_root() / "sandboxes")))


def bootstrap_admin_secret_path() -> Path:
    return secrets_dir() / "bootstrap_admin.txt"


def jwt_secret_file_path() -> Path:
    return Path(os.environ.get("JWT_SECRET_FILE", str(secrets_dir() / "jwt_secret.key")))


def firewall_rules_path() -> Path:
    return Path(
        os.environ.get(
            "AIFACTORY_FIREWALL_RULES_FILE",
            str(config_dir() / "firewall_rules.json"),
        )
    )


def batch_pipeline_queue_path() -> Path:
    return state_dir() / "batch_pipeline_queue.json"


def discussions_seed_marker_path() -> Path:
    return data_root() / "discussions" / ".seed_default_session"


def platform_pid_path() -> Path:
    return state_dir() / "platform.pid"


def director_rules_path() -> Path:
    return config_dir() / "director_rules.yaml"


def llm_pricing_config_path() -> Path:
    return Path(
        os.environ.get(
            "AIFACTORY_LLM_PRICING_YAML",
            str(config_dir() / "llm_pricing.yaml"),
        )
    )


def encrypted_vault_path() -> Path:
    return Path(
        os.environ.get(
            "AIFACTORY_SECRETS_VAULT_FILE",
            str(secrets_dir() / "encrypted_vault.json"),
        )
    )


def secrets_master_key_path() -> Path:
    return Path(
        os.environ.get(
            "AIFACTORY_SECRETS_MASTER_KEY_FILE",
            str(secrets_dir() / "master.key"),
        )
    )


def support_director_queue_path() -> Path:
    return Path(
        os.environ.get(
            "AIFACTORY_SUPPORT_DIRECTOR_QUEUE",
            str(support_root_dir() / "director_queue.jsonl"),
        )
    )


def config_path() -> Path:
    """Primary platform YAML path (same resolution as :func:`core.config_merge.config_yaml_path` unless overridden)."""
    p = os.environ.get("AIFACTORY_CONFIG_PATH")
    if p:
        return Path(p)
    from core.config_merge import config_yaml_path

    return config_yaml_path()


def state_dir() -> Path:
    return Path(os.environ.get("AIFACTORY_STATE_DIR", str(data_root() / "state")))


def logs_dir() -> Path:
    return Path(os.environ.get("AIFACTORY_LOGS_DIR", str(data_root() / "logs")))


def pipeline_json_path() -> Path:
    return Path(os.environ.get("AICOM_PIPELINE_JSON", str(state_dir() / "pipeline.json")))


def pipeline_db_path() -> Path:
    return Path(os.environ.get("SQLITE_PATH", str(state_dir() / "pipeline.db")))


def workspace_id() -> str:
    return os.environ.get("AIFACTORY_WORKSPACE_ID", "default").strip() or "default"


def model_providers_path() -> Path:
    return Path(
        os.environ.get(
            "AIFACTORY_MODEL_PROVIDERS",
            str(data_root() / "config" / "model_providers.yaml"),
        )
    )


def code_dir(product_id: str) -> Path:
    return data_root() / "code" / product_id


def specs_dir(product_id: str) -> Path:
    return data_root() / "specs" / product_id


def product_state_dir(product_id: str) -> Path:
    return state_dir() / product_id


def agent_artifact_dir(agent_type: str, product_id: str) -> Path:
    return data_root() / agent_type / product_id


def pending_payments_path() -> Path:
    return state_dir() / "pending_payments.json"


def sandbox_registry_path() -> Path:
    return state_dir() / "sandboxes.json"


def admin_users_path() -> Path:
    return Path(os.environ.get("ADMIN_USERS_PATH", str(data_root() / "config" / "admin_users.json")))


def legacy_admin_path() -> Path:
    return data_root() / "config" / "admin.json"


def chat_messages_path() -> Path:
    return state_dir() / "chat_messages.json"


def arch_dir(product_id: str) -> Path:
    return data_root() / "arch" / product_id


def telemetry_dir(product_id: str) -> Path:
    return data_root() / "telemetry" / product_id


def reports_dir() -> Path:
    return data_root() / "reports"


def benchmarks_reports_dir() -> Path:
    return reports_dir() / "benchmarks"


def director_trigger_signal_path() -> Path:
    return state_dir() / "director_trigger.signal"


def director_decisions_path() -> Path:
    return state_dir() / "director_decisions.json"


def benchmark_status_path() -> Path:
    return state_dir() / "benchmark_status.json"


def metrics_history_path() -> Path:
    return logs_dir() / "metrics_history.jsonl"


def escalations_log_path() -> Path:
    return logs_dir() / "escalations.jsonl"


def legacy_audit_log_path() -> Path:
    return logs_dir() / "audit.jsonl"


def audit_log_dir() -> Path:
    return logs_dir() / "audit"


def llm_calls_log_path() -> Path:
    return logs_dir() / "llm_calls.jsonl"


def director_reports_dir() -> Path:
    return reports_dir() / "director"


def benchmark_scorecard_path() -> Path:
    return reports_dir() / "benchmark_scorecard.json"


def benchmark_alerts_path() -> Path:
    return reports_dir() / "benchmark_alerts.json"


def discovery_dir() -> Path:
    return data_root() / "discovery"


def marketing_content_path(product_id: str) -> Path:
    return product_state_dir(product_id) / "marketing_content.json"


def market_research_path(product_id: str) -> Path:
    return product_state_dir(product_id) / "market_research.json"


def specification_path(product_id: str) -> Path:
    return specs_dir(product_id) / "specification.json"


def architecture_json_path(product_id: str) -> Path:
    return arch_dir(product_id) / "architecture.json"


def feedback_dir() -> Path:
    return data_root() / "feedback"


def bugs_dir(product_id: str) -> Path:
    return data_root() / "bugs" / product_id


def store_dir() -> Path:
    return data_root() / "store"


def store_licenses_path() -> Path:
    return store_dir() / "licenses.json"


def ai_market_integrations_log_path() -> Path:
    return logs_dir() / "ai_market_integrations.jsonl"


def support_root_dir() -> Path:
    return data_root() / "support"


def support_sessions_dir() -> Path:
    return Path(
        os.environ.get(
            "AIFACTORY_SUPPORT_SESSIONS_DIR",
            str(support_root_dir() / "sessions"),
        )
    )


def marketing_logs_dir() -> Path:
    return logs_dir() / "marketing"


def discussions_dir() -> Path:
    return data_root() / "discussions"


def inspector_reports_dir() -> Path:
    return reports_dir() / "inspector"


def customer_jwt_secret_path() -> Path:
    return Path(os.environ.get("CUSTOMER_JWT_SECRET_FILE", str(secrets_dir() / "customer_jwt.key")))


def owner_general_directives_path() -> Path:
    return state_dir() / "owner_general_directives.json"


def feedback_state_dir() -> Path:
    return state_dir() / "feedback"


def security_data_dir(product_id: str) -> Path:
    return data_root() / "security" / product_id
