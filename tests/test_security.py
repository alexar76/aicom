# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Security Tests
# ============================================================================
# Tests for security/ modules and web/backend/core/security.py
# Covers: Firewall, Secrets Manager, Audit Logger, Sandbox, SecurityManager
# ============================================================================

import pytest
import json
import time
from pathlib import Path

from security.firewall import FirewallManager, FirewallRule
from security.secrets_manager import SecretsManager
from security.audit_logger import AuditLogger, AuditEntry
from security.sandbox_isolation import SandboxIsolation, SandboxStatus
from web.backend.core.security import SecurityManager


# ============================================================================
# Firewall Tests
# ============================================================================

class TestFirewallManager:
    """Tests for the Firewall Manager."""

    @pytest.fixture
    def firewall(self, temp_data_dir):
        rules_file = temp_data_dir / "config" / "firewall_rules.json"
        fw = FirewallManager(str(rules_file))
        fw.clear_rules()
        return fw

    def test_default_deny(self, firewall):
        allowed, reason = firewall.is_allowed("192.168.1.1", 8080)
        assert not allowed
        assert "no_matching_allow_rule" in reason

    def test_whitelist_ip(self, firewall):
        firewall.whitelist_ip("192.168.1.100", "Test whitelist")
        allowed, reason = firewall.is_allowed("192.168.1.100", 8080)
        assert allowed

    def test_blacklist_ip(self, firewall):
        firewall.whitelist_ip("10.0.0.1", "Allow first")
        firewall.blacklist_ip("10.0.0.1", "Then block")
        allowed, reason = firewall.is_allowed("10.0.0.1", 8080)
        assert not allowed
        assert "denied_by_rule" in reason

    def test_rate_limiting(self, firewall):
        firewall.set_rate_limit(3, 60)
        for _ in range(3):
            firewall.record_request("10.0.0.2")
        firewall.record_request("10.0.0.2")
        allowed, reason = firewall.is_allowed("10.0.0.2", 8080)
        assert not allowed
        assert "rate_limited" in reason

    def test_brute_force_protection(self, firewall):
        firewall.brute_force_threshold = 3
        firewall.brute_force_block_duration = 60
        for _ in range(3):
            firewall.record_failed_attempt("10.0.0.3")
        allowed, reason = firewall.is_allowed("10.0.0.3", 8080)
        assert not allowed

    def test_port_filtering(self, firewall):
        firewall.whitelist_ip("10.0.0.4")
        firewall.deny_port(9000)
        allowed, reason = firewall.is_allowed("10.0.0.4", 9000)
        assert not allowed
        assert "port_not_allowed" in reason

    def test_rule_persistence(self, firewall, temp_data_dir):
        firewall.whitelist_ip("10.0.0.5", "Persistent rule")
        rules_file = temp_data_dir / "config" / "firewall_rules.json"
        firewall2 = FirewallManager(str(rules_file))
        allowed, reason = firewall2.is_allowed("10.0.0.5", 8080)
        assert allowed

    def test_security_scan(self, firewall):
        firewall.whitelist_ip("10.0.0.6")
        scan = firewall.run_security_scan()
        assert "open_ports" in scan
        assert "total_rules" in scan
        assert "risk_level" in scan

    def test_cidr_rules(self, firewall):
        firewall.add_rule(FirewallRule(
            id="allow_subnet",
            action="allow",
            source="10.0.0.0/24",
            description="Allow subnet",
        ))
        allowed, reason = firewall.is_allowed("10.0.0.50", 8080)
        assert allowed
        not_allowed, _ = firewall.is_allowed("10.1.0.50", 8080)
        assert not not_allowed


# ============================================================================
# Secrets Manager Tests
# ============================================================================

class TestSecretsManager:
    """Tests for the Secrets Manager."""

    @pytest.fixture
    def secrets(self, temp_data_dir):
        sm = SecretsManager(
            secrets_file=str(temp_data_dir / "secrets" / "encrypted_vault.json"),
            master_key_file=str(temp_data_dir / "secrets" / "master.key"),
            cache_ttl_seconds=1,
        )
        return sm

    def test_set_and_get_secret(self, secrets):
        secrets.set_secret("api_key_test", "sk-test123")
        value = secrets.get_secret("api_key_test")
        assert value == "sk-test123"

    def test_secret_overwrite_protection(self, secrets):
        secrets.set_secret("important_key", "original_value")
        result = secrets.set_secret("important_key", "new_value", overwrite=False)
        assert not result
        value = secrets.get_secret("important_key")
        assert value == "original_value"

    def test_secret_deletion(self, secrets):
        secrets.set_secret("temp_key", "temp_value")
        assert secrets.get_secret("temp_key") == "temp_value"
        secrets.delete_secret("temp_key")
        assert secrets.get_secret("temp_key") is None

    def test_nonexistent_secret(self, secrets):
        value = secrets.get_secret("nonexistent", "default_value")
        assert value == "default_value"

    def test_encryption_at_rest(self, secrets, temp_data_dir):
        secrets.set_secret("sensitive", "top_secret_value")
        vault_file = temp_data_dir / "secrets" / "encrypted_vault.json"
        raw_content = vault_file.read_bytes()
        assert b"top_secret_value" not in raw_content

    def test_key_rotation(self, secrets):
        secrets.set_secret("key_to_rotate", "value")
        secrets.rotate_master_key()
        value = secrets.get_secret("key_to_rotate")
        assert value == "value"

    def test_list_secrets(self, secrets):
        secrets.set_secret("secret_a", "value_a")
        secrets.set_secret("secret_b", "value_b")
        keys = secrets.list_secrets()
        assert "secret_a" in keys
        assert "secret_b" in keys

    def test_backup_vault(self, secrets):
        secrets.set_secret("backup_test", "backup_value")
        backup_path = secrets.backup_vault()
        assert Path(backup_path).exists()

    def test_api_key_convenience(self, secrets):
        secrets.set_api_key("openai", "sk-openai-test")
        assert secrets.get_api_key("openai") == "sk-openai-test"


# ============================================================================
# Audit Logger Tests
# ============================================================================

class TestAuditLogger:
    """Tests for the Audit Logger."""

    @pytest.fixture
    def audit(self, temp_data_dir):
        log_dir = temp_data_dir / "logs" / "audit"
        al = AuditLogger(str(log_dir), max_file_size_mb=1, max_log_files=3)
        return al

    def test_log_entry(self, audit):
        entry = audit.log(
            action="test_action",
            actor="test_actor",
            resource="test_resource",
            details={"key": "value"},
            severity="info",
        )
        assert entry.action == "test_action"
        assert entry.actor == "test_actor"
        assert entry.hash is not None

    def test_hash_chain(self, audit):
        entry1 = audit.log("action1", "actor1", "resource1", {})
        entry2 = audit.log("action2", "actor2", "resource2", {})
        assert entry2.previous_hash == entry1.hash

    def test_query_filtering(self, audit):
        audit.log("login", "admin", "auth", {"success": True})
        audit.log("logout", "admin", "auth", {})
        audit.log("config_change", "admin", "config", {"setting": "theme"})
        results = audit.query(action_filter="login")
        assert len(results) == 1
        assert results[0].action == "login"
        results = audit.query(actor_filter="admin")
        assert len(results) == 3

    def test_integrity_verification(self, audit):
        audit.log("action1", "actor1", "resource1", {})
        audit.log("action2", "actor2", "resource2", {})
        result = audit.verify_integrity()
        assert result["verified"] is True

    def test_tamper_detection(self, audit):
        audit.log("action1", "actor1", "resource1", {})
        log_file = list(audit.log_dir.glob("audit-*.jsonl"))[0]
        content = log_file.read_text()
        tampered = content.replace("action1", "EVIL_ACTION")
        log_file.write_text(tampered)
        result = audit.verify_integrity()
        assert result["verified"] is False

    def test_severity_levels(self, audit):
        audit.info("info_action", "actor", "resource", {})
        audit.warning("warn_action", "actor", "resource", {})
        audit.error("err_action", "actor", "resource", {})
        audit.critical("crit_action", "actor", "resource", {})
        results = audit.query()
        severities = [e.severity for e in results]
        assert "info" in severities
        assert "warning" in severities
        assert "error" in severities
        assert "critical" in severities

    def test_log_rotation(self, audit):
        for i in range(100):
            audit.log(f"action_{i}", "actor", "resource", {"i": i})
        log_files = list(audit.log_dir.glob("audit-*.jsonl"))
        assert len(log_files) <= 3

    def test_audit_entry_format(self, audit):
        """Verify the format of an audit entry."""
        entry = audit.log("deploy", "admin", "pipeline/42", {"env": "prod"}, "info")
        assert isinstance(entry, AuditEntry)
        assert entry.timestamp > 0
        assert entry.action == "deploy"
        assert entry.actor == "admin"
        assert entry.resource == "pipeline/42"
        assert entry.details == {"env": "prod"}
        assert entry.severity == "info"
        assert entry.hash is not None
        assert len(entry.hash) == 64  # SHA-256 hex
        assert entry.previous_hash != ""  # Chained

    def test_export_json(self, audit, tmp_path):
        """Export to JSON produces a valid file."""
        audit.log("action1", "actor1", "resource1", {})
        out = tmp_path / "export.json"
        count = audit.export_json(str(out))
        assert count == 1
        data = json.loads(out.read_text())
        assert len(data) == 1
        assert data[0]["action"] == "action1"

    def test_export_csv(self, audit, tmp_path):
        """Export to CSV produces a valid file."""
        audit.log("action1", "actor1", "resource1", {})
        out = tmp_path / "export.csv"
        count = audit.export_csv(str(out))
        assert count == 1
        assert out.exists()


# ============================================================================
# Sandbox Isolation Tests
# ============================================================================

class TestSandboxIsolation:
    """Tests for Sandbox Isolation."""

    @pytest.fixture
    def sandbox(self, temp_data_dir):
        sb = SandboxIsolation(
            sandbox_base_dir=str(temp_data_dir / "sandboxes"),
            port_range_start=19000,
            port_range_end=19050,
            max_sandboxes=5,
        )
        return sb

    def test_create_sandbox(self, sandbox, temp_data_dir):
        code_dir = temp_data_dir / "code" / "test_product"
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / "main.py").write_text("print('hello')")
        sb = sandbox.create_sandbox("test_product", str(code_dir))
        assert sb.id is not None
        assert sb.product_id == "test_product"
        assert sb.status == SandboxStatus.CREATED
        assert sb.port is not None

    def test_sandbox_limits(self, sandbox, temp_data_dir):
        sandbox.max_sandboxes = 2
        code_dir = temp_data_dir / "code" / "test"
        code_dir.mkdir(parents=True, exist_ok=True)
        sandbox.create_sandbox("p1", str(code_dir))
        sandbox.create_sandbox("p2", str(code_dir))
        with pytest.raises(RuntimeError, match="Maximum sandboxes"):
            sandbox.create_sandbox("p3", str(code_dir))

    def test_get_active_sandboxes(self, sandbox, temp_data_dir):
        code_dir = temp_data_dir / "code" / "test"
        code_dir.mkdir(parents=True, exist_ok=True)
        sb = sandbox.create_sandbox("p1", str(code_dir))
        active = sandbox.get_active_sandboxes()
        assert len(active) == 0  # Not started yet

    def test_sandbox_persistence(self, sandbox, temp_data_dir):
        code_dir = temp_data_dir / "code" / "test"
        code_dir.mkdir(parents=True, exist_ok=True)
        sb = sandbox.create_sandbox("p1", str(code_dir))
        sandbox2 = SandboxIsolation(
            sandbox_base_dir=str(temp_data_dir / "sandboxes"),
            port_range_start=19000,
            port_range_end=19050,
        )
        loaded = sandbox2.get_sandbox(sb.id)
        assert loaded is not None
        assert loaded.product_id == "p1"

    def test_destroy_sandbox(self, sandbox, temp_data_dir):
        code_dir = temp_data_dir / "code" / "test"
        code_dir.mkdir(parents=True, exist_ok=True)
        sb = sandbox.create_sandbox("p1", str(code_dir))
        sandbox.destroy_sandbox(sb.id)
        assert sandbox.get_sandbox(sb.id) is None

    def test_cleanup_all(self, sandbox, temp_data_dir):
        code_dir = temp_data_dir / "code" / "test"
        code_dir.mkdir(parents=True, exist_ok=True)
        sandbox.create_sandbox("p1", str(code_dir))
        sandbox.create_sandbox("p2", str(code_dir))
        count = sandbox.cleanup_all()
        assert count == 2
        assert len(sandbox.sandboxes) == 0


# ============================================================================
# SecurityManager (JWT / Password / Audit) Tests
# ============================================================================

class TestSecurityManager:
    """Tests for the SecurityManager (JWT, password, audit)."""

    @pytest.fixture
    def sm(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        return SecurityManager(
            secret_key="test-secret-key-12345-for-testing-only",
            jwt_algorithm="HS256",
            jwt_expiry_minutes=30,
            max_login_attempts=5,
            ban_minutes=15,
            audit_log_path=str(audit_path),
        )

    # ------------------------------------------------------------------
    # Password hashing
    # ------------------------------------------------------------------

    def test_hash_and_verify_password(self, sm):
        """Hashed password can be verified against plaintext."""
        hashed = sm.hash_password("my_secure_password")
        assert hashed != "my_secure_password"
        assert sm.verify_password("my_secure_password", hashed) is True

    def test_verify_wrong_password(self, sm):
        """Wrong password does not verify."""
        hashed = sm.hash_password("correct_password")
        assert sm.verify_password("wrong_password", hashed) is False

    def test_verify_empty_password(self, sm):
        """Empty password hashing and verification."""
        hashed = sm.hash_password("")
        assert sm.verify_password("", hashed) is True

    # ------------------------------------------------------------------
    # JWT token creation / verification
    # ------------------------------------------------------------------

    def test_create_access_token(self, sm):
        """JWT token is created with correct claims."""
        token = sm.create_access_token("admin_user", is_admin=True)
        assert token is not None
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # header.payload.signature

    def test_decode_valid_token(self, sm):
        """Valid token decodes to correct payload."""
        token = sm.create_access_token("test_admin", is_admin=True)
        payload = sm.decode_token(token)
        assert payload is not None
        assert payload["sub"] == "test_admin"
        assert payload["admin"] is True
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload

    def test_decode_token_non_admin(self, sm):
        """Non-admin token has admin=False."""
        token = sm.create_access_token("viewer", is_admin=False)
        payload = sm.decode_token(token)
        assert payload is not None
        assert payload["admin"] is False

    def test_decode_invalid_token(self, sm):
        """Malformed token returns None."""
        payload = sm.decode_token("invalid.token.here")
        assert payload is None

    def test_decode_tampered_token(self, sm):
        """Tampered token (wrong signature) returns None."""
        token = sm.create_access_token("admin", is_admin=True)
        parts = token.split(".")
        # Tamper with payload
        import base64
        tampered_payload = base64.urlsafe_b64encode(b'{"sub": "hacker"}').rstrip(b"=").decode()
        parts[1] = tampered_payload
        bad_token = ".".join(parts)
        payload = sm.decode_token(bad_token)
        assert payload is None

    def test_token_expiry(self, sm):
        """Token expires after jwt_expiry_minutes."""
        sm.jwt_expiry_minutes = 0  # Expire immediately
        token = sm.create_access_token("admin", is_admin=True)
        import time
        time.sleep(0.1)  # Ensure token has expired
        payload = sm.decode_token(token)
        # With 0 expiry, token may be already expired
        assert payload is None

    # ------------------------------------------------------------------
    # Login attempt tracking
    # ------------------------------------------------------------------

    def test_check_login_attempts_within_limit(self, sm):
        """Under limit → allowed."""
        assert sm.check_login_attempts("10.0.0.1") is True

    def test_check_login_attempts_exceeded(self, sm):
        """Over limit → blocked."""
        sm.max_login_attempts = 3
        for _ in range(3):
            sm.record_login_attempt("10.0.0.2", False)
        assert sm.check_login_attempts("10.0.0.2") is False

    def test_login_attempts_reset_after_window(self, sm):
        """After ban window passes, attempts are allowed again."""
        sm.max_login_attempts = 2
        sm.ban_minutes = 0  # Immediate expiry
        sm.record_login_attempt("10.0.0.3", False)
        sm.record_login_attempt("10.0.0.3", False)
        # With ban_minutes=0, the window is 0 seconds, so old attempts are cleaned
        assert sm.check_login_attempts("10.0.0.3") is True

    # ------------------------------------------------------------------
    # Audit log integration
    # ------------------------------------------------------------------

    def test_audit_log_created(self, sm, tmp_path):
        """Login attempts create hash-chain audit log entries."""
        sm.record_login_attempt("10.0.0.100", True, "test_user")
        chain_dir = tmp_path / "logs" / "audit"
        assert chain_dir.is_dir()
        assert list(chain_dir.glob("audit-*.jsonl"))

    def test_audit_log_format(self, sm):
        """Audit entry has correct fields (via get_audit_logs)."""
        sm.record_login_attempt("10.0.0.101", False, "bad_user")
        logs = sm.get_audit_logs(limit=1)
        assert logs
        entry = logs[-1]
        assert entry["action"] == "login_attempt"
        assert entry["username"] == "bad_user"
        assert entry["success"] is False
        assert entry["ip_address"] == "10.0.0.101"

    def test_get_audit_logs(self, sm):
        """Retrieving audit logs returns recent entries."""
        sm.record_login_attempt("10.0.0.1", True, "user1")
        sm.record_login_attempt("10.0.0.2", False, "user2")
        logs = sm.get_audit_logs(limit=10)
        assert len(logs) == 2

    def test_get_audit_logs_filtered(self, sm):
        """Audit logs can be filtered by action."""
        sm.record_login_attempt("10.0.0.1", True, "user1")
        logs = sm.get_audit_logs(action_filter="login_attempt")
        assert len(logs) == 1
        logs = sm.get_audit_logs(action_filter="nonexistent")
        assert len(logs) == 0

    def test_audit_log_timestamp_filter(self, sm):
        """Audit logs filtered since a timestamp."""
        sm.record_login_attempt("10.0.0.1", True, "user1")
        time.sleep(0.01)
        now = time.time()
        sm.record_login_attempt("10.0.0.2", True, "user2")
        logs = sm.get_audit_logs(since=now)
        assert len(logs) == 1

    def test_export_audit_logs_json(self, sm):
        """Export audit logs as JSON string."""
        sm.record_login_attempt("10.0.0.1", True, "user1")
        exported = sm.export_audit_logs(format="json")
        data = json.loads(exported)
        assert len(data) == 1

    def test_export_audit_logs_csv(self, sm):
        """Export audit logs as CSV string."""
        sm.record_login_attempt("10.0.0.1", True, "user1")
        exported = sm.export_audit_logs(format="csv")
        assert "action" in exported
        assert "login_attempt" in exported
