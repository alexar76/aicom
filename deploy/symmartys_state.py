#!/usr/bin/env python3
"""Prepare state-preserving SYMMARTYS deployment settings without sourcing .env."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

PUBLIC_URL = "https://modelmarket.dev/providers/symmartys"
ENV_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def destination(explicit: str | None = None, legacy: Path = Path("/opt/emporion"),
                current: Path = Path("/opt/symmartys")) -> Path:
    chosen = Path(explicit) if explicit else legacy if legacy.exists() else current
    if not chosen.is_absolute() or ".." in chosen.parts or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(chosen)):
        raise ValueError("--dest must be an absolute path without spaces or parent traversal")
    return chosen


def literal(raw: str, key: str) -> str:
    value = raw.strip()
    if value[:1] in ("'", '"'):
        if len(value) < 2 or value[-1] != value[0]:
            raise ValueError(f"{key}: multiline values require manual migration")
        value = value[1:-1]
    if any(c in value for c in ("\n", "\r", "$", "`")):
        raise ValueError(f"{key} must contain a literal value")
    return value


def prepare_env(path: Path, *, fresh: bool = False) -> tuple[str, dict]:
    if not path.is_file():
        raise ValueError("Create the installation .env with an explicit SYMMARTYS_VOLUME_NAME first")
    original = path.read_text()
    lines = original.splitlines()
    values: dict[str, str] = {}
    positions: dict[str, int] = {}
    for index, line in enumerate(lines):
        match = ENV_LINE.match(line)
        if not match:
            continue
        key, raw = match.groups()
        if key in values:
            raise ValueError(f"Duplicate environment key: {key}")
        values[key], positions[key] = raw, index
    added, changed = [], []

    def put(key: str, raw: str) -> None:
        if key in positions:
            if values[key] == raw:
                return
            lines[positions[key]] = f"{key}={raw}"
            changed.append(key)
        else:
            positions[key] = len(lines)
            lines.append(f"{key}={raw}")
            added.append(key)
        values[key] = raw

    old_public = literal(values.get("EMPORION_PUBLIC_URL", ""), "EMPORION_PUBLIC_URL")
    for key, raw in list(values.items()):
        if not key.startswith("EMPORION_"):
            continue
        current = "SYMMARTYS_" + key[len("EMPORION_"):]
        if current in values:
            continue
        # Validate quoted legacy settings before copying their raw spelling. Secrets and
        # shell metacharacters are not evaluated, normalized or printed.
        if raw.strip()[:1] in ("'", '"') and (len(raw.strip()) < 2 or raw.strip()[-1:] != raw.strip()[:1]):
            raise ValueError(f"{key}: multiline values require manual migration")
        if key == "EMPORION_PUBLIC_URL" and (
            "/providers/emporion" in old_public or "emporion.modelmarket.dev" in old_public
        ):
            raw = PUBLIC_URL
        put(current, raw)
    if "SYMMARTYS_PUBLIC_URL" not in values:
        put("SYMMARTYS_PUBLIC_URL", PUBLIC_URL)
    for key, default in (("ORACLE_PQC", "1"), ("SYMMARTYS_CORS_ORIGINS", "https://alexar76.github.io")):
        if key not in values:
            put(key, default)

    public = literal(values["SYMMARTYS_PUBLIC_URL"], "SYMMARTYS_PUBLIC_URL")
    url = urlsplit(public)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
        raise ValueError("SYMMARTYS_PUBLIC_URL must be a public base URL without credentials")
    aliases_raw = values.get("ORACLE_HUB_AUDIENCES", "")
    aliases = literal(aliases_raw, "ORACLE_HUB_AUDIENCES")
    retained = [a.strip().rstrip("/") for a in aliases.split(",") if a.strip()]
    for base in (old_public, public):
        if base and base.rstrip("/") not in retained:
            retained.append(base.rstrip("/"))
    if retained != [a.strip().rstrip("/") for a in aliases.split(",") if a.strip()]:
        put("ORACLE_HUB_AUDIENCES", ",".join(retained))

    volume = literal(values.get("SYMMARTYS_VOLUME_NAME", ""), "SYMMARTYS_VOLUME_NAME")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", volume) or volume in (".", ".."):
        raise ValueError("Set SYMMARTYS_VOLUME_NAME explicitly to the existing Docker data volume")
    expected = literal(values.get("SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY", ""), "SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY")
    if not fresh and not expected:
        raise ValueError("Upgrades require SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY from the existing manifest")
    if expected:
        try:
            valid = len(base64.b64decode(expected, validate=True)) == 32
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY must encode the existing 32-byte public key")
    return "\n".join(lines) + "\n", {
        "env_file": str(path), "keys_added": added, "keys_changed": changed,
        "volume_name": volume, "public_url": public,
        "expected_signer_configured": bool(expected), "fresh_identity_requested": fresh,
    }


def apply_env(path: Path, *, fresh: bool = False) -> dict:
    prepared, summary = prepare_env(path, fresh=fresh)
    if prepared == path.read_text():
        return summary
    backup = path.with_name(path.name + ".before-symmartys")
    try:
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass  # Never replace the original pre-migration environment backup.
    else:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(path.read_text())
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(prepared)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)
    return summary


def render_vhost(template: Path, dest: Path, output: Path) -> None:
    text = template.read_text()
    marker = "@@SYMMARTYS_LANDING_ROOT@@"
    if marker not in text:
        raise ValueError("nginx template has no installation-root marker")
    output.write_text(text.replace(marker, str(dest / "src/symmartys/docs/landing")))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("destination", "plan", "apply", "volume", "public-url", "expected-key", "render-vhost"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--dest")
    parser.add_argument("--fresh-volume", action="store_true")
    parser.add_argument("--template", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "destination":
            print(destination(args.dest))
        elif args.command == "render-vhost":
            if not args.template or not args.output:
                raise ValueError("render-vhost requires --template and --output")
            render_vhost(args.template, destination(args.dest), args.output)
        else:
            if not args.env_file:
                raise ValueError("--env-file is required")
            _, summary = prepare_env(args.env_file, fresh=args.fresh_volume)
            if args.command == "apply":
                summary = apply_env(args.env_file, fresh=args.fresh_volume)
            if args.command in ("plan", "apply"):
                print(json.dumps(summary, indent=2))
            elif args.command == "volume":
                print(summary["volume_name"])
            elif args.command == "public-url":
                print(summary["public_url"])
            elif args.command == "expected-key":
                for line in args.env_file.read_text().splitlines():
                    match = ENV_LINE.match(line)
                    if match and match[1] == "SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY":
                        print(literal(match[2], match[1]))
                        break
    except ValueError as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
