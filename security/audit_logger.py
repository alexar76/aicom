# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Audit Logger
# ============================================================================
# Provides tamper-evident audit logging for all security-relevant events.
# Uses hash chaining to detect log tampering.
# ============================================================================

import json
import os
import time
import hashlib
import logging
import re
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("ai_factory.security.audit")
GENESIS_HASH = hashlib.sha256(b"AI_FACTORY_AUDIT_GENESIS").hexdigest()
_AUDIT_FNAME = re.compile(r"^audit-(\d{8})-(\d{6})(?:-(\d+))?\.jsonl$")


def _audit_log_files_chrono(log_dir: Path, *, reverse: bool = False) -> List[Path]:
    """
    Chronological order for ``audit-*.jsonl``.

    Lexical sort breaks when a same-second collision file ``audit-T-NNN.jsonl`` sorts
    before ``audit-T.jsonl``. ``st_mtime`` alone can tie on coarse filesystem timestamps.
    """

    def sort_key(p: Path) -> tuple:
        m = _AUDIT_FNAME.match(p.name)
        if not m:
            try:
                return (0, 0, 0, p.stat().st_mtime_ns, p.name)
            except OSError:
                return (0, 0, 0, 0, p.name)
        day, hms, suf = m.group(1), m.group(2), m.group(3)
        core = int(day) * 1_000_000 + int(hms)
        suf_i = -1 if suf is None else int(suf)
        try:
            ns = p.stat().st_mtime_ns
        except OSError:
            ns = 0
        return (core, suf_i, ns, p.name)

    files = list(log_dir.glob("audit-*.jsonl"))
    files.sort(key=sort_key)
    if reverse:
        files.reverse()
    return files


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """A single audit log entry with hash chain integrity."""
    timestamp: float
    action: str           # e.g., "login", "logout", "config_change", "pipeline_action"
    actor: str            # e.g., "admin", "system", "agent:pm"
    resource: str         # e.g., "auth", "pipeline/123", "config/theme"
    details: Dict[str, Any]
    severity: str         # "info", "warning", "error", "critical"
    ip_address: str = ""
    session_id: str = ""
    previous_hash: str = ""
    hash: str = ""

    def compute_hash(self) -> str:
        """Compute the hash of this entry."""
        content = f"{self.timestamp}|{self.action}|{self.actor}|{self.resource}|{json.dumps(self.details, sort_keys=True)}|{self.severity}|{self.ip_address}|{self.session_id}|{self.previous_hash}"
        return hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Audit Logger
# ---------------------------------------------------------------------------

class AuditLogger:
    """
    Tamper-evident audit logger with hash chaining.
    
    Features:
    - Hash chain: each entry contains hash of previous entry
    - Integrity verification: detect any tampering
    - JSONL format for easy parsing
    - Automatic log rotation (by size)
    - Search and filtering capabilities
    - Export to multiple formats
    """

    def __init__(
        self,
        log_dir: str | None = None,
        max_file_size_mb: int = 100,
        max_log_files: int = 10,
    ):
        from core.paths import audit_log_dir

        self.log_dir = Path(log_dir) if log_dir else audit_log_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.max_log_files = max_log_files
        
        self._current_file: Optional[Path] = None
        self._last_hash: str = ""
        self._lock_file: Optional[Path] = None
        
        self._initialize()

    # -----------------------------------------------------------------------
    # Initialization
    # -----------------------------------------------------------------------

    def _initialize(self) -> None:
        """Initialize the audit logger."""
        # Create integrity lock file
        self._lock_file = self.log_dir / ".integrity.lock"
        
        # Find the latest log file
        log_files = _audit_log_files_chrono(self.log_dir)
        if log_files:
            self._current_file = log_files[-1]
            # Get last hash from the last entry
            self._last_hash = self._get_last_hash()
        else:
            self._rotate()
        if not self._last_hash:
            self._last_hash = GENESIS_HASH
        
        logger.info(f"Audit logger initialized: {self._current_file}")

    def _get_current_file(self) -> Path:
        """Get the current log file, rotating if needed."""
        if self._current_file:
            try:
                if not self._current_file.exists():
                    self._current_file.parent.mkdir(parents=True, exist_ok=True)
                    self._current_file.touch(exist_ok=True)
                if self._current_file.stat().st_size < self.max_file_size:
                    return self._current_file
            except FileNotFoundError:
                pass
        self._rotate()
        return self._current_file

    def _rotate(self) -> None:
        """Rotate to a new log file."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        base = time.strftime("%Y%m%d-%H%M%S")
        candidate = self.log_dir / f"audit-{base}.jsonl"
        if candidate.exists():
            candidate = self.log_dir / f"audit-{base}-{int(time.time() * 1000) % 1000:03d}.jsonl"
        self._current_file = candidate
        self._current_file.touch(exist_ok=True)
        
        # Clean up old files
        log_files = _audit_log_files_chrono(self.log_dir)
        while len(log_files) > self.max_log_files:
            oldest = log_files.pop(0)
            oldest.unlink()
            logger.info(f"Removed old audit log: {oldest}")

    def _get_last_hash(self) -> str:
        """Get the hash of the last entry in the newest audit log file."""
        log_files = _audit_log_files_chrono(self.log_dir)
        if not log_files:
            return ""
        for log_file in reversed(log_files):
            if not log_file.exists():
                continue
            try:
                lines = log_file.read_text(encoding="utf-8").strip().split("\n")
                if lines and lines[-1]:
                    last_entry = json.loads(lines[-1])
                    h = last_entry.get("hash", "")
                    if h:
                        return str(h)
            except Exception:
                continue
        return ""

    def _sync_last_hash_from_disk(self) -> None:
        """Align in-memory chain tip with the last persisted entry (crash-safe)."""
        disk_hash = self._get_last_hash()
        if disk_hash:
            self._last_hash = disk_hash
        elif not self._last_hash:
            self._last_hash = GENESIS_HASH

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------

    def log(
        self,
        action: str,
        actor: str,
        resource: str,
        details: Dict[str, Any] = None,
        severity: str = "info",
        ip_address: str = "",
        session_id: str = "",
    ) -> AuditEntry:
        """
        Log an audit event.
        Returns the created AuditEntry.
        """
        self._sync_last_hash_from_disk()

        entry = AuditEntry(
            timestamp=time.time(),
            action=action,
            actor=actor,
            resource=resource,
            details=details or {},
            severity=severity,
            ip_address=ip_address,
            session_id=session_id,
            previous_hash=self._last_hash,
        )
        entry.hash = entry.compute_hash()
        prior_hash = self._last_hash
        # Advance chain in memory before durable write so a crash after append cannot desync.
        self._last_hash = entry.hash

        log_file = self._get_current_file()
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            self._last_hash = prior_hash
            logger.error(f"Failed to write audit log: {e}")
            raise
        
        # Also log to system logger for critical events
        if severity in ("warning", "error", "critical"):
            log_method = getattr(logger, severity, logger.warning)
            log_method(f"AUDIT: {action} by {actor} on {resource}: {details}")
        
        return entry

    # Convenience methods
    def info(self, action: str, actor: str, resource: str, details: Dict[str, Any] = None, ip: str = "", session: str = "") -> AuditEntry:
        return self.log(action, actor, resource, details, "info", ip, session)

    def warning(self, action: str, actor: str, resource: str, details: Dict[str, Any] = None, ip: str = "", session: str = "") -> AuditEntry:
        return self.log(action, actor, resource, details, "warning", ip, session)

    def error(self, action: str, actor: str, resource: str, details: Dict[str, Any] = None, ip: str = "", session: str = "") -> AuditEntry:
        return self.log(action, actor, resource, details, "error", ip, session)

    def critical(self, action: str, actor: str, resource: str, details: Dict[str, Any] = None, ip: str = "", session: str = "") -> AuditEntry:
        return self.log(action, actor, resource, details, "critical", ip, session)

    # -----------------------------------------------------------------------
    # Querying
    # -----------------------------------------------------------------------

    def query(
        self,
        limit: int = 100,
        offset: int = 0,
        action_filter: Optional[str] = None,
        actor_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
    ) -> List[AuditEntry]:
        """
        Query audit logs with filters.
        Returns entries in reverse chronological order (newest first).
        """
        results = []
        
        for log_file in _audit_log_files_chrono(self.log_dir, reverse=True):
            try:
                lines = log_file.read_text().strip().split("\n")
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        entry = AuditEntry(**data)
                    except Exception:
                        continue
                    
                    # Apply filters
                    if action_filter and action_filter not in entry.action:
                        continue
                    if actor_filter and actor_filter not in entry.actor:
                        continue
                    if severity_filter and entry.severity != severity_filter:
                        continue
                    if since and entry.timestamp < since:
                        continue
                    if until and entry.timestamp > until:
                        continue
                    
                    results.append(entry)
                    if len(results) >= offset + limit:
                        break
                
                if len(results) >= offset + limit:
                    break
            except Exception as e:
                logger.warning(f"Error reading audit log {log_file}: {e}")
        
        return results[offset:offset + limit]

    # -----------------------------------------------------------------------
    # Integrity Verification
    # -----------------------------------------------------------------------

    def verify_integrity(self) -> Dict[str, Any]:
        """
        Verify the integrity of all audit logs.
        Checks hash chain continuity.
        Returns verification results.
        """
        result = {
            "verified": True,
            "files_checked": 0,
            "entries_checked": 0,
            "tampered_entries": [],
            "errors": [],
        }
        
        previous_hash = GENESIS_HASH

        for log_file in _audit_log_files_chrono(self.log_dir):
            result["files_checked"] += 1
            try:
                lines = log_file.read_text().strip().split("\n")
                for i, line in enumerate(lines):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        entry = AuditEntry(**data)
                    except Exception as e:
                        result["errors"].append(f"{log_file.name}:{i+1} - Parse error: {e}")
                        result["verified"] = False
                        continue

                    result["entries_checked"] += 1

                    # Verify entry hash matches canonical payload
                    expected_hash = entry.compute_hash()
                    if entry.hash != expected_hash:
                        result["tampered_entries"].append({
                            "file": log_file.name,
                            "line": i + 1,
                            "action": entry.action,
                            "timestamp": entry.timestamp,
                        })
                        result["verified"] = False

                    # Verify chain (continues across rotated log files)
                    if entry.previous_hash != previous_hash:
                        result["tampered_entries"].append({
                            "file": log_file.name,
                            "line": i + 1,
                            "action": entry.action,
                            "reason": "hash_chain_break",
                        })
                        result["verified"] = False

                    previous_hash = entry.hash
            except Exception as e:
                result["errors"].append(f"{log_file.name}: {e}")
                result["verified"] = False
        
        return result

    # -----------------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------------

    def export_json(self, output_path: str, filters: Dict = None) -> int:
        """Export audit logs to a JSON file. Returns number of entries."""
        entries = self.query(limit=1000000, **(filters or {}))
        data = [asdict(e) for e in entries]
        Path(output_path).write_text(json.dumps(data, indent=2))
        return len(entries)

    def export_csv(self, output_path: str, filters: Dict = None) -> int:
        """Export audit logs to a CSV file. Returns number of entries."""
        entries = self.query(limit=1000000, **(filters or {}))
        if not entries:
            return 0
        
        import csv
        fieldnames = list(asdict(entries[0]).keys())
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in entries:
                writer.writerow(asdict(entry))
        return len(entries)
