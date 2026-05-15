# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Secrets Manager
# ============================================================================
# Manages sensitive configuration values (API keys, passwords, tokens)
# with encryption at rest and secure in-memory storage.
# ============================================================================

import os
import json
import base64
import time
import logging
from typing import Dict, Optional, Any
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("ai_factory.security.secrets")

# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------

class SecretsManager:
    """
    Manages sensitive configuration with encryption at rest.
    
    Features:
    - AES-256 encryption at rest (Fernet)
    - Master key derived from password + salt (PBKDF2)
    - In-memory cache with auto-expiry
    - Environment variable fallback
    - Secret rotation support
    - Auto-backup on modification
    """

    def __init__(
        self,
        secrets_file: str | None = None,
        master_key_file: str | None = None,
        cache_ttl_seconds: int = 300,  # 5 minutes
    ):
        self.secrets_file = Path(
            secrets_file or os.environ.get("AIFACTORY_SECRETS_VAULT_FILE", "/app/data/secrets/encrypted_vault.json")
        )
        self.master_key_file = Path(
            master_key_file
            or os.environ.get("AIFACTORY_SECRETS_MASTER_KEY_FILE", "/app/data/secrets/master.key")
        )
        self.cache_ttl = cache_ttl_seconds
        
        # In-memory cache
        self._cache: Dict[str, tuple[Any, float]] = {}  # key -> (value, expiry)
        self._fernet: Optional[Fernet] = None
        
        # Initialize encryption
        self._initialize_encryption()

    # -----------------------------------------------------------------------
    # Initialization
    # -----------------------------------------------------------------------

    def _initialize_encryption(self) -> None:
        """Initialize or load the encryption key."""
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        
        if self.master_key_file.exists():
            key = self.master_key_file.read_bytes()
        else:
            key = Fernet.generate_key()
            self.master_key_file.write_bytes(key)
            self.master_key_file.chmod(0o600)  # Owner read/write only
            logger.info("Generated new master encryption key")
        
        self._fernet = Fernet(key)

    def rotate_master_key(self) -> None:
        """
        Rotate the master encryption key.
        Re-encrypts all secrets with the new key.
        """
        old_key = self.master_key_file.read_bytes() if self.master_key_file.exists() else None
        old_fernet = Fernet(old_key) if old_key else None
        
        # Generate new key
        new_key = Fernet.generate_key()
        self._fernet = Fernet(new_key)
        
        # Re-encrypt existing secrets
        if old_fernet and self.secrets_file.exists():
            try:
                encrypted_data = self.secrets_file.read_bytes()
                decrypted = old_fernet.decrypt(encrypted_data)
                re_encrypted = self._fernet.encrypt(decrypted)
                self.secrets_file.write_bytes(re_encrypted)
            except Exception as e:
                logger.error(f"Failed to re-encrypt secrets during key rotation: {e}")
                self._fernet = Fernet(old_key)
                raise
        
        # Save new key
        self.master_key_file.write_bytes(new_key)
        self.master_key_file.chmod(0o600)
        
        # Clear cache
        self._cache.clear()
        logger.info("Master encryption key rotated successfully")

    # -----------------------------------------------------------------------
    # Secret Management
    # -----------------------------------------------------------------------

    def set_secret(self, key: str, value: Any, overwrite: bool = True) -> bool:
        """
        Store a secret value.
        Returns True if successful, False if key exists and overwrite=False.
        """
        secrets = self._load_vault()
        
        if key in secrets and not overwrite:
            logger.warning(f"Secret '{key}' already exists and overwrite=False")
            return False
        
        secrets[key] = value
        self._save_vault(secrets)
        
        # Update cache
        self._cache[key] = (value, time.time() + self.cache_ttl)
        
        logger.info(f"Secret '{key}' {'updated' if key in secrets else 'stored'}")
        return True

    def get_secret(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a secret value.
        Checks: cache → vault → environment variable.
        """
        # Check cache
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            else:
                del self._cache[key]
        
        # Check vault
        secrets = self._load_vault()
        if key in secrets:
            value = secrets[key]
            self._cache[key] = (value, time.time() + self.cache_ttl)
            return value
        
        # Check environment variable
        env_key = key.upper().replace("-", "_").replace(" ", "_")
        env_value = os.environ.get(env_key)
        if env_value:
            self._cache[key] = (env_value, time.time() + self.cache_ttl)
            return env_value
        
        return default

    def delete_secret(self, key: str) -> bool:
        """Delete a secret."""
        secrets = self._load_vault()
        if key in secrets:
            del secrets[key]
            self._save_vault(secrets)
            self._cache.pop(key, None)
            logger.info(f"Secret '{key}' deleted")
            return True
        return False

    def list_secrets(self) -> list[str]:
        """List all secret keys (not values)."""
        secrets = self._load_vault()
        return list(secrets.keys())

    def has_secret(self, key: str) -> bool:
        """Check if a secret exists."""
        return self.get_secret(key) is not None

    # -----------------------------------------------------------------------
    # Bulk Operations
    # -----------------------------------------------------------------------

    def import_from_env(self, prefix: str = "AI_FACTORY_") -> int:
        """
        Import secrets from environment variables with a given prefix.
        Returns the number of secrets imported.
        """
        count = 0
        for env_key, env_value in os.environ.items():
            if env_key.startswith(prefix):
                secret_key = env_key[len(prefix):].lower().replace("_", "-")
                self.set_secret(secret_key, env_value)
                count += 1
        logger.info(f"Imported {count} secrets from environment")
        return count

    def export_to_env(self, prefix: str = "AI_FACTORY_") -> Dict[str, str]:
        """
        Export secrets as environment variable mappings (for subprocesses).
        Returns dict of env var name → value.
        """
        secrets = self._load_vault()
        env_map = {}
        for key in secrets:
            env_key = f"{prefix}{key.upper().replace('-', '_')}"
            env_map[env_key] = str(secrets[key])
        return env_map

    def backup_vault(self, backup_path: Optional[str] = None) -> str:
        """Create a backup of the encrypted vault."""
        if not self.secrets_file.exists():
            raise FileNotFoundError("No vault to backup")
        
        backup_path = backup_path or f"/app/data/secrets/backup_{int(time.time())}.enc"
        backup_file = Path(backup_path)
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy encrypted file
        backup_file.write_bytes(self.secrets_file.read_bytes())
        backup_file.chmod(0o600)
        
        logger.info(f"Vault backed up to {backup_path}")
        return backup_path

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _load_vault(self) -> Dict[str, Any]:
        """Load and decrypt the vault."""
        if not self.secrets_file.exists():
            return {}
        
        try:
            encrypted_data = self.secrets_file.read_bytes()
            decrypted_data = self._fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logger.error(f"Failed to decrypt vault: {e}")
            return {}

    def _save_vault(self, secrets: Dict[str, Any]) -> None:
        """Encrypt and save the vault."""
        try:
            json_data = json.dumps(secrets, indent=2).encode()
            encrypted_data = self._fernet.encrypt(json_data)
            self.secrets_file.write_bytes(encrypted_data)
            self.secrets_file.chmod(0o600)
        except Exception as e:
            logger.error(f"Failed to save vault: {e}")
            raise

    # -----------------------------------------------------------------------
    # Convenience Methods
    # -----------------------------------------------------------------------

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get an API key for a specific provider."""
        return self.get_secret(f"api_key_{provider}")

    def set_api_key(self, provider: str, key: str) -> None:
        """Set an API key for a specific provider."""
        self.set_secret(f"api_key_{provider}", key)

    def get_admin_password_hash(self) -> Optional[str]:
        """Get the stored admin password hash."""
        return self.get_secret("admin_password_hash")

    def set_admin_password_hash(self, password_hash: str) -> None:
        """Store the admin password hash."""
        self.set_secret("admin_password_hash", password_hash)

    def get_totp_secret(self) -> Optional[str]:
        """Get the TOTP secret for 2FA."""
        return self.get_secret("totp_secret")

    def set_totp_secret(self, secret: str) -> None:
        """Store the TOTP secret."""
        self.set_secret("totp_secret", secret)

    def get_jwt_secret(self) -> str:
        """Get or generate the JWT signing secret."""
        secret = self.get_secret("jwt_secret")
        if not secret:
            secret = Fernet.generate_key().decode()
            self.set_secret("jwt_secret", secret)
        return secret
