"""Shell injection guards for remote SSH commands."""

from __future__ import annotations

import os
import re
import shlex

_SHELL_METACHAR_RE = re.compile(r"[;&|`$()]|\$\(")
_DOCKER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")


def quote_shell(value: str) -> str:
    return shlex.quote(value)


def assert_safe_shell_word(value: str, *, label: str) -> str:
    """Reject values that could break out of a quoted shell argument."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{label} is empty")
    if any(ch in cleaned for ch in "\n\r\0"):
        raise ValueError(f"{label} contains invalid characters")
    if cleaned.startswith("-"):
        raise ValueError(f"{label} must not start with '-'")
    if _SHELL_METACHAR_RE.search(cleaned):
        raise ValueError(f"{label} contains shell metacharacters")
    return cleaned


def validate_log_path(path: str) -> str:
    cleaned = assert_safe_shell_word(path, label="Log path")
    if not cleaned.startswith("/"):
        raise ValueError("Log path must be an absolute path")
    # "/var/log/../../etc/shadow" is absolute and free of metacharacters, so the
    # checks above wave it through. Requiring an already-normalised path means the
    # allow-list a wrapper enforces on prefixes cannot be walked out of.
    if ".." in cleaned.split("/"):
        raise ValueError("Log path must not contain '..'")
    return cleaned


def validate_docker_name(name: str) -> str:
    cleaned = assert_safe_shell_word(name, label="Docker container name")
    if not _DOCKER_NAME_RE.match(cleaned):
        raise ValueError("Docker container name has invalid characters")
    return cleaned


def custom_ssh_commands_allowed() -> bool:
    return os.environ.get("SKOPOS_ALLOW_CUSTOM_SSH_COMMANDS", "").lower() in ("1", "true", "yes")


def validate_custom_ssh_command(command: str) -> str:
    """Allow simple read-only commands; block chaining when custom commands are enabled."""
    cleaned = (command or "").strip()
    if not cleaned:
        raise ValueError("Command is empty")
    if any(ch in cleaned for ch in "\n\r\0"):
        raise ValueError("Command contains invalid characters")
    if _SHELL_METACHAR_RE.search(cleaned):
        raise ValueError("Custom commands must not contain shell metacharacters (; | & ` $())")
    return cleaned
