"""
Security Manager
================
Handles authentication, authorization, and audit logging for the admin panel.
Supports JWT + HTTP-only cookies, 2FA (TOTP), and brute-force protection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext

from web.backend.core.oidc_auth import username_from_trusted_header
from web.backend.http.client_ip import client_ip
from core.jwt_tokens import decode_hs256_optional, encode_hs256
from core.paths import jwt_secret_file_path, legacy_admin_path, legacy_audit_log_path
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)

# Minimum length for JWT HMAC keys loaded from env or jwt_secret.key file.
_JWT_MIN_KEY_CHARS = 32


def resolve_jwt_secret_for_runtime(explicit: Optional[str]) -> str:
    """
    Resolve HS256 secret for JWT. Callers may pass ``explicit`` (unit tests).
    Production: set ``JWT_SECRET_KEY`` (>=32 chars) or rely on Docker entrypoint
    ``jwt_secret.key`` mounted at ``JWT_SECRET_FILE``.
    """
    if explicit is not None:
        s = explicit.strip()
        if len(s) >= 8:
            return s
    env = (os.environ.get("JWT_SECRET_KEY") or "").strip()
    # Ignore empty compose placeholders; prefer jwt_secret.key when env is blank.
    if len(env) >= _JWT_MIN_KEY_CHARS:
        return env
    key_path = jwt_secret_file_path()
    if key_path.is_file():
        from_file = key_path.read_text(encoding="utf-8").strip()
        if len(from_file) >= _JWT_MIN_KEY_CHARS:
            return from_file
    if os.environ.get("AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL", "").lower() in ("1", "true", "yes"):
        logger.warning(
            "JWT: AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL=1 — using ephemeral secret; "
            "all sessions invalidated on restart. Do not use in production."
        )
        return hashlib.sha256(os.urandom(48)).hexdigest()
    raise RuntimeError(
        "JWT signing key missing or too short. Set JWT_SECRET_KEY (>=32 characters), "
        "or mount /app/data/secrets/jwt_secret.key (see entrypoint.sh). "
        "For disposable local runs only: AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL=1"
    )


# Password hashing context.
# Prefer pbkdf2_sha256 for reliable cross-environment behavior in CI/containers.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Security scheme
security_scheme = HTTPBearer(auto_error=False)


class SecurityManager:
    """
    Manages authentication and authorization.
    
    Features:
    - JWT token generation and validation
    - Password hashing with bcrypt
    - 2FA (TOTP) support
    - Brute-force protection
    - Audit logging
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        jwt_algorithm: str = "HS256",
        jwt_expiry_minutes: int = 30,
        max_login_attempts: int = 5,
        ban_minutes: int = 15,
        audit_log_path: str | None = None,
    ):
        self.secret_key = resolve_jwt_secret_for_runtime(secret_key)
        self.jwt_algorithm = jwt_algorithm
        self.jwt_expiry_minutes = jwt_expiry_minutes
        self.max_login_attempts = max_login_attempts
        self.ban_minutes = ban_minutes
        self.audit_log_path = audit_log_path or str(legacy_audit_log_path())

        self._audit_chain: Any = None
        chain_dir = Path(self.audit_log_path).parent / "audit"
        try:
            from security.audit_logger import AuditLogger

            self._audit_chain = AuditLogger(log_dir=str(chain_dir))
        except Exception as e:
            logger.warning("SecurityManager: hash-chain AuditLogger unavailable (%s)", e)

        # Persistent rate limiting (SQLite) with in-memory fallback
        self._login_attempts: dict[str, list[float]] = {}
        self._rl_store = self._init_rate_limit_store()

        # Ensure audit log directory exists
        Path(self.audit_log_path).parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _init_rate_limit_store():
        try:
            from core.persistent_security_store import get_persistent_security_store

            return get_persistent_security_store()
        except Exception as exc:
            logger.warning("SecurityManager: rate-limit store unavailable (%s)", exc)
            return None

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash.
        Supports bcrypt (passlib) and SHA256+salt (fallback for init).
        """
        # Try bcrypt first
        try:
            if pwd_context.verify(plain_password, hashed_password):
                return True
        except Exception as exc:
            logger.debug("bcrypt verify failed, trying legacy hash", exc_info=exc)

        # Try SHA256+salt fallback
        try:
            admin_file = legacy_admin_path()
            if admin_file.exists():
                import json
                with open(admin_file) as f:
                    cfg = json.load(f)
                salt = cfg.get("hash_salt", "")
                hash_type = cfg.get("hash_type", "")
                if hash_type == "sha256_salted" and salt:
                    expected = hashlib.sha256((plain_password + salt).encode()).hexdigest()
                    return secrets.compare_digest(expected, hashed_password)
        except Exception as exc:
            logger.debug("legacy sha256 password verify failed", exc_info=exc)

        return False

    def create_access_token(
        self,
        username: str,
        is_admin: bool = True,
        role: Optional[str] = None,
    ) -> str:
        """Create a JWT access token. `role` is one of viewer|operator|admin|super_admin."""
        now = datetime.now(timezone.utc)
        if self.jwt_expiry_minutes <= 0:
            expiry = now - timedelta(seconds=1)
        else:
            expiry = now + timedelta(minutes=self.jwt_expiry_minutes)
        r = (role or "super_admin").strip().lower()
        payload = {
            "sub": username,
            "admin": is_admin,
            "role": r,
            "exp": expiry,
            "iat": now,
            "jti": hashlib.sha256(os.urandom(32)).hexdigest()[:16],
        }
        return encode_hs256(payload, self.secret_key, algorithm=self.jwt_algorithm)

    def decode_token(self, token: str) -> Optional[dict]:
        """Decode and validate a JWT token."""
        payload = decode_hs256_optional(
            token, self.secret_key, algorithms=[self.jwt_algorithm]
        )
        if payload is None:
            logger.warning("Token validation failed")
        return payload

    def check_login_attempts(self, ip_address: str) -> bool:
        """Check if login attempts are within limits."""
        window = self.ban_minutes * 60
        if self._rl_store is not None:
            attempts = self._rl_store.recent_attempt_count(ip_address, window)
            return attempts < self.max_login_attempts

        now = time.time()
        if ip_address in self._login_attempts:
            self._login_attempts[ip_address] = [
                t for t in self._login_attempts[ip_address]
                if now - t < window
            ]
        attempts = self._login_attempts.get(ip_address, [])
        return len(attempts) < self.max_login_attempts

    def record_login_attempt(self, ip_address: str, success: bool, username: str = ""):
        """Record a login attempt for rate limiting and audit."""
        if success:
            self.reset_login_attempts(ip_address)
        elif self._rl_store is not None:
            self._rl_store.record_attempt(ip_address)
        else:
            if ip_address not in self._login_attempts:
                self._login_attempts[ip_address] = []
            self._login_attempts[ip_address].append(time.time())

        # Audit log
        self._audit_log({
            "action": "login_attempt",
            "username": username,
            "ip_address": ip_address,
            "success": success,
            "timestamp": time.time(),
        })

    def reset_login_attempts(self, ip_address: str) -> None:
        """Clear recorded attempts for an IP (e.g. after successful login)."""
        if self._rl_store is not None:
            self._rl_store.clear_attempts(ip_address)
        self._login_attempts.pop(ip_address, None)

    def generate_totp_secret(self) -> str:
        """Generate a TOTP secret for 2FA."""
        import pyotp
        return pyotp.random_base32()

    def get_totp_uri(self, secret: str, username: str) -> str:
        """Get the TOTP provisioning URI for QR code."""
        import pyotp
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=username, issuer_name="AI-Factory")

    def verify_totp(self, secret: str, code: str) -> bool:
        """Verify a TOTP code."""
        import pyotp
        totp = pyotp.TOTP(secret)
        return totp.verify(code)

    def _audit_log(self, entry: dict):
        """Write audit events — prefer tamper-evident hash-chain; legacy JSONL is fallback only."""
        if self._audit_chain is not None:
            try:
                sev = "error" if entry.get("success") is False else "info"
                self._audit_chain.log(
                    action=str(entry.get("action", "event")),
                    actor=str(entry.get("username") or entry.get("sub") or "unknown"),
                    resource=str(entry.get("resource") or "admin/auth"),
                    details=entry,
                    severity=sev,
                    ip_address=str(entry.get("ip_address", "")),
                )
                return
            except Exception as e:
                logger.error("Failed to write hash-chain audit: %s", e)
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)

    def get_audit_logs(
        self,
        limit: int = 100,
        action_filter: Optional[str] = None,
        since: Optional[float] = None,
    ) -> list[dict]:
        """Get audit log entries with optional filtering (hash-chain preferred)."""
        if self._audit_chain is not None:
            from dataclasses import asdict

            rows = self._audit_chain.query(
                limit=limit,
                action_filter=action_filter,
                since=since,
            )
            out: list[dict] = []
            for row in reversed(rows):
                d = asdict(row)
                details = d.get("details") if isinstance(d.get("details"), dict) else {}
                legacy = dict(details)
                legacy.setdefault("action", d.get("action"))
                legacy.setdefault("timestamp", d.get("timestamp"))
                legacy.setdefault("username", d.get("actor"))
                legacy.setdefault("ip_address", d.get("ip_address"))
                if action_filter and legacy.get("action") != action_filter:
                    continue
                out.append(legacy)
            return out[-limit:]

        entries: list[dict] = []
        try:
            with open(self.audit_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            if action_filter and entry.get("action") != action_filter:
                                continue
                            if since and entry.get("timestamp", 0) < since:
                                continue
                            entries.append(entry)
                        except json.JSONDecodeError as _suppressed_exc:
                            log_suppressed(logger, "non-fatal (web/backend/core/security.py)", exc_info=_suppressed_exc)
        except FileNotFoundError as _suppressed_exc:
            log_suppressed(logger, "non-fatal (web/backend/core/security.py)", exc_info=_suppressed_exc)

        return entries[-limit:]

    def export_audit_logs(self, format: str = "json") -> str:
        """Export audit logs in JSON or CSV format."""
        entries = self.get_audit_logs(limit=10000)
        
        if format == "csv":
            import csv
            import io
            output = io.StringIO()
            if entries:
                writer = csv.DictWriter(output, fieldnames=entries[0].keys())
                writer.writeheader()
                writer.writerows(entries)
            return output.getvalue()
        
        return json.dumps(entries, indent=2)


async def get_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> dict:
    """
    Dependency for protecting admin routes.
    Validates JWT token from Authorization header or cookie.
    """
    token = None

    # Trusted reverse-proxy SSO (Authelia / oauth2-proxy / Keycloak gate)
    peer_ip = client_ip(request)
    hdr_user = username_from_trusted_header(dict(request.headers), peer_ip)
    if hdr_user:
        return {
            "sub": hdr_user,
            "username": hdr_user,
            "admin": True,
            "role": (os.environ.get("AIFACTORY_SSO_TRUSTED_DEFAULT_ROLE") or "admin"),
            "sso": "trusted-header",
        }

    # Try Authorization header first
    if credentials:
        token = credentials.credentials

    # Try cookies (access_token legacy + aif_admin_session HttpOnly session)
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        token = request.cookies.get("aif_admin_session")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    security_manager = getattr(request.app.state, "security_manager", None)
    if not security_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security manager not initialized",
        )

    payload = security_manager.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if not payload.get("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    return payload
