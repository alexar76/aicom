# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Firewall Manager
# ============================================================================
# Implements IP-based access control, rate limiting, and request filtering
# for the platform's web interface and API endpoints.
# ============================================================================

import ipaddress
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.logging_utils import log_suppressed

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover
    Fernet = None  # type: ignore[misc, assignment]
    InvalidToken = ValueError  # type: ignore[misc, assignment]

logger = logging.getLogger("ai_factory.security.firewall")

_ENCRYPTED_V1 = "aicom_encrypted"

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class FirewallRule:
    """A single firewall rule."""
    id: str
    action: str  # "allow" | "deny"
    source: str  # IP, CIDR, or "all"
    protocol: str = "tcp"
    port: int | None = None
    description: str = ""
    enabled: bool = True
    created_at: float = field(default_factory=time.time)

    def matches(self, ip: str, port: int) -> bool:
        """Check if this rule matches the given IP and port."""
        if not self.enabled:
            return False
        if self.port is not None and self.port != port:
            return False
        if self.source == "all":
            return True
        try:
            if self.source == ip:
                return True
            if "/" in self.source and ipaddress.ip_address(ip) in ipaddress.ip_network(self.source, strict=False):
                return True
        except ValueError as _suppressed_exc:
            log_suppressed(logger, "non-fatal (security/firewall.py)", exc_info=_suppressed_exc)
        return False


@dataclass
class RateLimitEntry:
    """Tracks request count for rate limiting."""
    count: int = 0
    window_start: float = field(default_factory=time.time)
    blocked_until: float = 0.0


# ---------------------------------------------------------------------------
# Firewall Manager
# ---------------------------------------------------------------------------

class FirewallManager:
    """
    Manages IP-based access control, rate limiting, and request filtering.
    
    Features:
    - IP whitelist/blacklist with CIDR support
    - Per-IP rate limiting with configurable windows
    - Port-based filtering
    - Brute-force protection (temporary blocks)
    - Persistent rule storage
    """

    def __init__(
        self,
        rules_file: str | None = None,
        *,
        fernet_key: str | None = None,
    ):
        from core.paths import firewall_rules_path

        self.rules_file = Path(rules_file) if rules_file else firewall_rules_path()
        self._fernet_key_override = fernet_key
        self.rules: list[FirewallRule] = []
        self.rate_limits: dict[str, RateLimitEntry] = {}
        
        # Default rate limits (requests per window)
        self.default_rate_limit: int = 100       # requests
        self.default_rate_window: float = 60.0   # seconds
        self.brute_force_threshold: int = 5      # failed attempts
        self.brute_force_block_duration: float = 900.0  # 15 minutes
        
        # Default allowed ports
        self.allowed_ports: set[int] = {80, 443, 8080, 3000, 8000}
        
        self._load_rules()
        self._ensure_default_rules()

    def _resolved_fernet_key(self) -> str | None:
        if self._fernet_key_override is not None:
            k = (self._fernet_key_override or "").strip()
            return k or None
        return (os.environ.get("AIFACTORY_FIREWALL_RULES_FERNET_KEY") or "").strip() or None

    def _fernet_cipher(self) -> Any | None:
        if Fernet is None:
            return None
        key = self._resolved_fernet_key()
        if not key:
            return None
        try:
            return Fernet(key.encode("ascii"))
        except Exception as e:
            logger.warning("AIFACTORY_FIREWALL_RULES_FERNET_KEY is invalid: %s", e)
            return None

    def _payload_dict(self) -> dict[str, Any]:
        return {
            "rules": [
                {
                    "id": r.id,
                    "action": r.action,
                    "source": r.source,
                    "protocol": r.protocol,
                    "port": r.port,
                    "description": r.description,
                    "enabled": r.enabled,
                    "created_at": r.created_at,
                }
                for r in self.rules
            ],
            "allowed_ports": sorted(self.allowed_ports),
        }

    def _apply_payload_dict(self, data: dict[str, Any]) -> None:
        self.rules = [FirewallRule(**r) for r in data.get("rules", [])]
        self.allowed_ports = set(data.get("allowed_ports", [80, 443, 8080, 3000, 8000]))

    # -----------------------------------------------------------------------
    # Rule Management
    # -----------------------------------------------------------------------

    def add_rule(self, rule: FirewallRule) -> None:
        """Add a new firewall rule."""
        self.rules.append(rule)
        self._save_rules()
        logger.info(f"Firewall rule added: {rule.action} {rule.source} port={rule.port}")

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        for i, rule in enumerate(self.rules):
            if rule.id == rule_id:
                self.rules.pop(i)
                self._save_rules()
                logger.info(f"Firewall rule removed: {rule_id}")
                return True
        return False

    def get_rules(self, enabled_only: bool = False) -> list[FirewallRule]:
        """Get all rules, optionally filtering to enabled only."""
        if enabled_only:
            return [r for r in self.rules if r.enabled]
        return self.rules.copy()

    def clear_rules(self) -> None:
        """Clear all rules and reset to defaults."""
        self.rules.clear()
        self._ensure_default_rules()
        self._save_rules()
        logger.info("Firewall rules reset to defaults")

    # -----------------------------------------------------------------------
    # Access Control
    # -----------------------------------------------------------------------

    def http_request_allowed(self, ip: str, port: int = 8081) -> tuple[bool, str]:
        """
        HTTP middleware policy: always enforce rate limits and explicit deny rules.
        Full default-deny ACL applies only when ``AIFACTORY_FIREWALL_ENFORCE=1``.
        """
        if self._is_rate_limited(ip):
            return False, "rate_limited"
        if self.is_blacklisted(ip):
            return False, "blacklisted"
        enforce = (os.environ.get("AIFACTORY_FIREWALL_ENFORCE") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if enforce:
            return self.is_allowed(ip, port)
        return True, "ok"

    def is_allowed(self, ip: str, port: int = 8080) -> tuple[bool, str]:
        """
        Check if an IP:port combination is allowed.
        Returns (allowed, reason).
        """
        # Check rate limits first
        if self._is_rate_limited(ip):
            return False, "rate_limited"

        # Check port is allowed
        if port not in self.allowed_ports:
            return False, f"port_not_allowed: {port}"

        # Check explicit deny rules first (except global default-deny fallback).
        for rule in self.rules:
            if rule.action != "deny":
                continue
            if rule.source == "all":
                continue
            if rule.matches(ip, port):
                return False, f"denied_by_rule: {rule.description}"

        # Check for allow rules
        for rule in self.rules:
            if rule.action == "allow" and rule.matches(ip, port):
                return True, "allowed_by_rule"

        # If a global deny-all rule exists, keep legacy reason text expected by tests.
        if any(r.action == "deny" and r.source == "all" and r.enabled for r in self.rules):
            return False, "no_matching_allow_rule"

        # Default: deny if no allow rule matches.
        return False, "no_matching_allow_rule"

    def whitelist_ip(self, ip: str, description: str = "") -> None:
        """Add an IP to the whitelist."""
        rule_id = f"allow_{ip}_{int(time.time())}"
        self.add_rule(FirewallRule(
            id=rule_id,
            action="allow",
            source=ip,
            description=description or f"Whitelist {ip}"
        ))

    def blacklist_ip(self, ip: str, description: str = "") -> None:
        """Add an IP to the blacklist."""
        rule_id = f"deny_{ip}_{int(time.time())}"
        self.add_rule(FirewallRule(
            id=rule_id,
            action="deny",
            source=ip,
            description=description or f"Blacklist {ip}"
        ))

    def is_whitelisted(self, ip: str) -> bool:
        """Check if an IP is explicitly whitelisted."""
        return any(
            r.action == "allow" and r.source == ip and r.enabled
            for r in self.rules
        )

    def is_blacklisted(self, ip: str) -> bool:
        """Check if an IP is explicitly blacklisted."""
        return any(
            r.action == "deny" and r.source == ip and r.enabled
            for r in self.rules
        )

    # -----------------------------------------------------------------------
    # Rate Limiting
    # -----------------------------------------------------------------------

    def set_rate_limit(self, requests: int, window_seconds: float) -> None:
        """Set the default rate limit."""
        self.default_rate_limit = requests
        self.default_rate_window = window_seconds
        logger.info(f"Rate limit set: {requests} requests per {window_seconds}s")

    def record_request(self, ip: str) -> None:
        """Record a request from an IP for rate limiting."""
        now = time.time()
        if ip not in self.rate_limits:
            self.rate_limits[ip] = RateLimitEntry()
        
        entry = self.rate_limits[ip]
        
        # Reset window if expired
        if now - entry.window_start > self.default_rate_window:
            entry.count = 0
            entry.window_start = now
        
        entry.count += 1

    def record_failed_attempt(self, ip: str) -> None:
        """Record a failed authentication attempt (brute-force tracking)."""
        self.record_request(ip)
        entry = self.rate_limits.get(ip)
        if entry and entry.count >= self.brute_force_threshold:
            entry.blocked_until = time.time() + self.brute_force_block_duration
            logger.warning(f"Brute force detected from {ip}, blocked for {self.brute_force_block_duration}s")

    def _is_rate_limited(self, ip: str) -> bool:
        """Check if an IP is currently rate limited."""
        now = time.time()
        entry = self.rate_limits.get(ip)
        
        if not entry:
            return False
        
        # Check temporary block
        if entry.blocked_until > now:
            return True
        
        # Check rate limit
        if now - entry.window_start > self.default_rate_window:
            return False
        
        return entry.count >= self.default_rate_limit

    def reset_rate_limit(self, ip: str) -> None:
        """Reset rate limiting for a specific IP."""
        self.rate_limits.pop(ip, None)
        logger.info(f"Rate limit reset for {ip}")

    # -----------------------------------------------------------------------
    # Port Management
    # -----------------------------------------------------------------------

    def allow_port(self, port: int) -> None:
        """Add a port to the allowed list."""
        self.allowed_ports.add(port)
        logger.info(f"Port {port} allowed")

    def deny_port(self, port: int) -> None:
        """Remove a port from the allowed list."""
        self.allowed_ports.discard(port)
        logger.info(f"Port {port} denied")

    # -----------------------------------------------------------------------
    # Security Scan
    # -----------------------------------------------------------------------

    def run_security_scan(self) -> dict:
        """
        Run a security scan and return findings.
        Checks: open ports, rate limit status, blocked IPs, rule coverage.
        """
        now = time.time()
        findings = {
            "open_ports": sorted(self.allowed_ports),
            "total_rules": len(self.rules),
            "enabled_rules": sum(1 for r in self.rules if r.enabled),
            "blocked_ips": sum(1 for e in self.rate_limits.values() if e.blocked_until > now),
            "rate_limited_ips": sum(1 for ip in self.rate_limits if self._is_rate_limited(ip)),
            "whitelisted_ips": [r.source for r in self.rules if r.action == "allow" and r.enabled],
            "blacklisted_ips": [r.source for r in self.rules if r.action == "deny" and r.enabled],
            "has_default_deny": any(r.source == "all" and r.action == "deny" for r in self.rules),
        }
        
        # Risk assessment
        risks = []
        if not findings["has_default_deny"]:
            risks.append("No default-deny rule: all IPs allowed by default")
        if findings["blocked_ips"] > 0:
            risks.append(f"{findings['blocked_ips']} IP(s) currently blocked for brute force")
        if findings["rate_limited_ips"] > 5:
            risks.append(f"High number of rate-limited IPs: {findings['rate_limited_ips']}")
        
        findings["risks"] = risks
        findings["risk_level"] = "high" if len(risks) > 2 else "medium" if risks else "low"
        
        return findings

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    def _load_rules(self) -> None:
        """Load rules from file (plain JSON or Fernet envelope when key is configured)."""
        try:
            if not self.rules_file.exists():
                return
            raw_text = self.rules_file.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                return

            if data.get(_ENCRYPTED_V1) is True:
                f = self._fernet_cipher()
                if not f:
                    logger.warning(
                        "Firewall rules file is encrypted but AIFACTORY_FIREWALL_RULES_FERNET_KEY is unset or invalid",
                    )
                    return
                token = data.get("payload")
                if not isinstance(token, str):
                    logger.warning("Encrypted firewall rules envelope missing payload")
                    return
                try:
                    plain = f.decrypt(token.encode("ascii"))
                    inner = json.loads(plain.decode("utf-8"))
                except InvalidToken:
                    logger.warning("Firewall rules decryption failed (wrong Fernet key?)")
                    return
                if not isinstance(inner, dict):
                    return
                self._apply_payload_dict(inner)
                logger.info("Loaded %d firewall rules (encrypted at rest)", len(self.rules))
                return

            self._apply_payload_dict(data)
            logger.info("Loaded %d firewall rules", len(self.rules))
        except Exception as e:
            logger.warning("Failed to load firewall rules: %s", e)

    def _save_rules(self) -> None:
        """Save rules to file (encrypt when ``AIFACTORY_FIREWALL_RULES_FERNET_KEY`` is set)."""
        try:
            self.rules_file.parent.mkdir(parents=True, exist_ok=True)
            payload = self._payload_dict()
            f = self._fernet_cipher()
            if f:
                token = f.encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
                envelope = {_ENCRYPTED_V1: True, "v": 1, "payload": token}
                self.rules_file.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
            else:
                self.rules_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save firewall rules: %s", e)

    def _ensure_default_rules(self) -> None:
        """Ensure default rules exist."""
        if not any(r.source == "all" and r.action == "deny" for r in self.rules):
            self.rules.append(FirewallRule(
                id="default_deny_all",
                action="deny",
                source="all",
                description="Default deny all traffic",
            ))
        if not any(r.source == "127.0.0.1" for r in self.rules):
            self.rules.append(FirewallRule(
                id="allow_localhost",
                action="allow",
                source="127.0.0.1",
                description="Allow localhost",
            ))
        if not any(r.source == "::1" for r in self.rules):
            self.rules.append(FirewallRule(
                id="allow_localhost_ipv6",
                action="allow",
                source="::1",
                description="Allow localhost IPv6",
            ))
