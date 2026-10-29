"""Keep provider credentials in private files, with public YAML references only.

References are basenames under the trusted data/secrets/llm directory. Neither
configuration paths nor symlinks may turn a provider key lookup into a file read
outside that directory. Existing inline keys are migrated without generating or
rotating credentials; environment/vault references remain supported.
"""

from __future__ import annotations

import copy
import hashlib
import os
import re
import stat
import uuid
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import yaml

from core.json_state import write_text_atomic
from core import paths
from security.compromised_credentials import reject_compromised_credential

_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_BUILTIN_FILES = {
    "deepseek_api": "deepseek_api_key",
    "openrouter_api": "openrouter_api_key",
}
_MAX_SECRET_BYTES = 64 * 1024


def _filename(value: Any) -> str:
    if not isinstance(value, str) or not _FILENAME.fullmatch(value):
        raise ValueError("Invalid provider secret reference")
    return value


@contextmanager
def _secret_directory(*, create: bool):
    # The data root is operator configuration. All descendants are opened using
    # directory descriptors and NOFOLLOW, so a swapped component cannot escape it.
    root = paths.data_root()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in ("secrets", "llm"):
            if create:
                with suppress(FileExistsError):
                    os.mkdir(component, mode=0o700, dir_fd=directory)
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory,
            )
            os.close(directory)
            directory = child
        yield directory
    finally:
        os.close(directory)


def _assert_regular(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Provider secret must be a private regular file")


def read_provider_secret(reference: str) -> str | None:
    name = _filename(reference)
    try:
        with _secret_directory(create=False) as directory:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                _assert_regular(os.fstat(fd))
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "rb", closefd=False) as handle:
                    raw = handle.read(_MAX_SECRET_BYTES + 1)
                if len(raw) > _MAX_SECRET_BYTES:
                    raise ValueError("Provider secret exceeds size limit")
            finally:
                os.close(fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("Unsafe or unreadable provider secret file") from exc
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("Invalid provider secret encoding") from exc
    reject_compromised_credential(value)
    return value or None


def write_provider_secret(reference: str, key: str) -> Path:
    name = _filename(reference)
    value = key.strip()
    reject_compromised_credential(value)
    if not value or len(value.encode("utf-8")) > _MAX_SECRET_BYTES:
        raise ValueError("Invalid provider credential")
    with _secret_directory(create=True) as directory:
        try:
            _assert_regular(os.stat(name, dir_fd=directory, follow_symlinks=False))
        except FileNotFoundError:
            pass
        temporary = f".{name}.{uuid.uuid4().hex}.tmp"
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                # Apply the exact private mode before writing, even under umask 0.
                os.fchmod(handle.fileno(), 0o600)
                handle.write(value + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=directory)
    return paths.data_root() / "secrets" / "llm" / name


def resolve_provider_api_key(provider: dict[str, Any]) -> str:
    """Resolve legacy inline, env/vault, or private-file credentials consistently."""
    inline = provider.get("api_key")
    if inline:
        value = str(inline).strip()
    else:
        value = ""
        env_name = provider.get("api_key_env")
        if isinstance(env_name, str) and env_name.strip():
            from security.secret_resolver import get_secret

            name = env_name.strip()
            value = (os.environ.get(name) or "").strip()
            if not value:
                value = str(get_secret(name, env_names=[name]) or "").strip()
        reference = provider.get("api_key_file")
        if not value and reference:
            value = read_provider_secret(reference) or ""
    reject_compromised_credential(value)
    return value


def provider_secret_reference(provider_name: str) -> str:
    return _BUILTIN_FILES.get(provider_name) or (
        "provider_" + hashlib.sha256(provider_name.encode("utf-8")).hexdigest() + ".key"
    )


def save_provider_config(path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    """Move inline credentials to private storage before atomically saving YAML."""
    public = copy.deepcopy(config)
    providers = public.get("providers", {})
    if isinstance(providers, dict):
        for name, provider in providers.items():
            if not isinstance(provider, dict):
                continue
            inline = provider.get("api_key")
            if inline:
                reference = provider_secret_reference(str(name))
                write_provider_secret(reference, str(inline))
                provider["api_key_file"] = reference
                # Inline had precedence over env in legacy configs. Clearing the
                # shadowed reference preserves the currently configured identity.
                provider["api_key_env"] = None
            if "api_key_file" in provider and provider["api_key_file"]:
                _filename(provider["api_key_file"])
            provider["api_key"] = None
    write_text_atomic(
        path,
        yaml.safe_dump(public, sort_keys=False, allow_unicode=True, default_flow_style=False),
        mode=0o600,
    )
    return public


def migrate_provider_secret_config(path: str | Path) -> bool:
    """Remove legacy inline keys on load, preserving all other provider settings."""
    target = Path(path)
    try:
        config = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        # Parser diagnostics reproduce source lines, including an inline key.
        raise ValueError("Invalid provider configuration") from None
    providers = config.get("providers", {}) if isinstance(config, dict) else {}
    if not isinstance(providers, dict) or not any(
        isinstance(p, dict) and p.get("api_key") for p in providers.values()
    ):
        return False
    save_provider_config(target, config)
    return True
