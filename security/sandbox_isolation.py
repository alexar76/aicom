# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Sandbox Isolation
# ============================================================================
# Provides isolated execution environments for running generated code
# and applications safely within the Docker container.
# ============================================================================

import os
import json
import time
import uuid
import shutil
import signal
import logging
import subprocess
import tempfile
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("ai_factory.security.sandbox")

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class SandboxStatus(Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    TIMEOUT = "timeout"

@dataclass
class Sandbox:
    """Represents an isolated sandbox environment."""
    id: str
    product_id: str
    status: SandboxStatus = SandboxStatus.CREATED
    port: Optional[int] = None
    work_dir: str = ""
    pid: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    stopped_at: Optional[float] = None
    timeout_seconds: int = 300  # 5 minutes default
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Sandbox Isolation
# ---------------------------------------------------------------------------

class SandboxIsolation:
    """
    Manages isolated execution environments for generated code.
    
    Features:
    - Each sandbox runs in its own temporary directory
    - Process-level isolation with PID tracking
    - Resource limits (CPU, memory, time)
    - Port allocation and management
    - Automatic cleanup on timeout
    - Health monitoring
    - Network isolation (configurable)
    """

    def __init__(
        self,
        sandbox_base_dir: str = "/app/data/sandboxes",
        port_range_start: int = 9000,
        port_range_end: int = 9999,
        max_sandboxes: int = 10,
        default_timeout: int = 300,
        enable_network: bool = False,
        execution_mode: str = "process",
        container_image: str = "python:3.12-slim",
    ):
        self.sandbox_base_dir = Path(sandbox_base_dir)
        self.sandbox_base_dir.mkdir(parents=True, exist_ok=True)
        
        self.port_range = range(port_range_start, port_range_end + 1)
        self.max_sandboxes = max_sandboxes
        self.default_timeout = default_timeout
        self.enable_network = enable_network
        self.execution_mode = execution_mode if execution_mode in {"process", "container"} else "process"
        self.container_image = container_image
        
        self.sandboxes: Dict[str, Sandbox] = {}
        self._allocated_ports: set = set()
        self._state_file = self.sandbox_base_dir / ".sandbox_state.json"
        
        self._load_state()

    # -----------------------------------------------------------------------
    # Sandbox Lifecycle
    # -----------------------------------------------------------------------

    def create_sandbox(
        self,
        product_id: str,
        code_dir: str,
        timeout_seconds: Optional[int] = None,
        metadata: Dict = None,
    ) -> Sandbox:
        """
        Create a new sandbox for a product.
        
        Args:
            product_id: The product to sandbox
            code_dir: Path to the generated code directory
            timeout_seconds: Max runtime before auto-kill
            metadata: Additional metadata
        
        Returns:
            Sandbox instance
        """
        # Check limits
        existing = len(self.sandboxes)
        if existing >= self.max_sandboxes:
            raise RuntimeError(f"Maximum sandboxes reached ({self.max_sandboxes})")
        
        sandbox_id = f"sandbox-{uuid.uuid4().hex[:12]}"
        work_dir = self.sandbox_base_dir / sandbox_id
        
        # Create sandbox directory and copy code
        work_dir.mkdir(parents=True, exist_ok=True)
        src_dir = Path(code_dir)
        if src_dir.exists():
            self._copy_code(src_dir, work_dir)
        
        # Allocate port
        port = self._allocate_port()
        
        sandbox = Sandbox(
            id=sandbox_id,
            product_id=product_id,
            status=SandboxStatus.CREATED,
            port=port,
            work_dir=str(work_dir),
            timeout_seconds=timeout_seconds or self.default_timeout,
            metadata=metadata or {},
        )
        
        self.sandboxes[sandbox_id] = sandbox
        self._save_state()
        
        logger.info(f"Sandbox {sandbox_id} created for product {product_id} on port {port}")
        return sandbox

    def start_sandbox(self, sandbox_id: str, command: Optional[List[str]] = None) -> Sandbox:
        """
        Start a sandbox by running the generated code.
        
        Args:
            sandbox_id: The sandbox to start
            command: Override command (default: auto-detect)
        
        Returns:
            Updated Sandbox instance
        """
        sandbox = self._get_sandbox(sandbox_id)
        
        if sandbox.status != SandboxStatus.CREATED:
            raise RuntimeError(f"Sandbox {sandbox_id} is in state {sandbox.status.value}, expected CREATED")
        
        sandbox.status = SandboxStatus.STARTING
        sandbox.started_at = time.time()
        
        try:
            work_dir = Path(sandbox.work_dir)
            
            # Auto-detect command if not provided
            if command is None:
                command = self._detect_start_command(work_dir)
            
            if not command:
                sandbox.status = SandboxStatus.FAILED
                sandbox.error = "No start command detected"
                self._save_state()
                return sandbox

            if self.execution_mode == "container" and self._start_container_sandbox(sandbox, command):
                self._save_state()
                return sandbox
            
            # Build environment
            env = os.environ.copy()
            env["SANDBOX_ID"] = sandbox_id
            env["SANDBOX_PORT"] = str(sandbox.port)
            env["SANDBOX_PRODUCT_ID"] = sandbox.product_id
            env["AI_FACTORY_SANDBOX"] = "1"
            
            if not self.enable_network:
                # Network isolation via environment hint
                env["SANDBOX_NETWORK_ISOLATED"] = "1"
            
            # Start process
            process = subprocess.Popen(
                command,
                cwd=str(work_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,  # Create process group for cleanup
            )
            
            sandbox.pid = process.pid
            sandbox.status = SandboxStatus.RUNNING
            
            logger.info(f"Sandbox {sandbox_id} started (PID: {process.pid}, command: {' '.join(command)})")
            
        except Exception as e:
            sandbox.status = SandboxStatus.FAILED
            sandbox.error = str(e)
            logger.error(f"Failed to start sandbox {sandbox_id}: {e}")
        
        self._save_state()
        return sandbox

    def _start_container_sandbox(self, sandbox: Sandbox, command: List[str]) -> bool:
        container_name = sandbox.id
        network_mode = "bridge" if self.enable_network else "none"
        command_text = " ".join(command)
        docker_cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", network_mode,
            "--memory", "512m",
            "--cpus", "0.5",
            "-w", "/workspace",
            "-v", f"{sandbox.work_dir}:/workspace",
            "-p", f"{sandbox.port}:{sandbox.port}",
            self.container_image,
            "sh", "-lc", command_text,
        ]
        try:
            proc = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                logger.warning("Container sandbox start failed: %s", proc.stderr.strip())
                return False
            container_id = (proc.stdout or "").strip()
            sandbox.metadata["container_id"] = container_id or container_name
            sandbox.pid = None
            sandbox.status = SandboxStatus.RUNNING
            logger.info("Sandbox %s started in container mode (%s)", sandbox.id, sandbox.metadata["container_id"])
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning("Container sandbox start unavailable (%s), falling back to process mode", e)
            return False

    def stop_sandbox(self, sandbox_id: str, force: bool = False) -> Sandbox:
        """
        Stop a running sandbox.
        
        Args:
            sandbox_id: The sandbox to stop
            force: If True, use SIGKILL instead of SIGTERM
        
        Returns:
            Updated Sandbox instance
        """
        sandbox = self._get_sandbox(sandbox_id)
        
        if sandbox.status not in (SandboxStatus.RUNNING, SandboxStatus.STARTING):
            logger.warning(f"Sandbox {sandbox_id} is not running (status: {sandbox.status.value})")
            return sandbox
        
        sandbox.status = SandboxStatus.STOPPING
        
        try:
            container_id = sandbox.metadata.get("container_id")
            if container_id:
                subprocess.run(["docker", "stop", container_id], capture_output=True, text=True, timeout=15)
                subprocess.run(["docker", "rm", container_id], capture_output=True, text=True, timeout=15)
                sandbox.metadata.pop("container_id", None)
                sandbox.pid = None
                sandbox.status = SandboxStatus.STOPPED
                sandbox.stopped_at = time.time()
                self._save_state()
                return sandbox
            if sandbox.pid:
                # Kill the entire process group
                pgid = os.getpgid(sandbox.pid)
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.killpg(pgid, sig)
                
                # Wait for process to die
                try:
                    os.waitpid(sandbox.pid, 0)
                except ChildProcessError:
                    pass  # Already reaped
                
                sandbox.pid = None
            
            sandbox.status = SandboxStatus.STOPPED
            sandbox.stopped_at = time.time()
            
            logger.info(f"Sandbox {sandbox_id} stopped {'(force)' if force else ''}")
            
        except Exception as e:
            sandbox.status = SandboxStatus.FAILED
            sandbox.error = str(e)
            logger.error(f"Failed to stop sandbox {sandbox_id}: {e}")
        
        self._save_state()
        return sandbox

    def destroy_sandbox(self, sandbox_id: str, cleanup_files: bool = True) -> None:
        """
        Destroy a sandbox and optionally clean up its files.
        
        Args:
            sandbox_id: The sandbox to destroy
            cleanup_files: If True, remove the sandbox directory
        """
        sandbox = self._get_sandbox(sandbox_id)
        
        # Stop if running
        if sandbox.status in (SandboxStatus.RUNNING, SandboxStatus.STARTING):
            self.stop_sandbox(sandbox_id, force=True)
        
        # Release port
        if sandbox.port:
            self._allocated_ports.discard(sandbox.port)
        
        # Clean up files
        if cleanup_files and sandbox.work_dir:
            work_dir = Path(sandbox.work_dir)
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)
        
        # Remove from tracking
        self.sandboxes.pop(sandbox_id, None)
        self._save_state()
        
        logger.info(f"Sandbox {sandbox_id} destroyed")

    # -----------------------------------------------------------------------
    # Monitoring
    # -----------------------------------------------------------------------

    def get_sandbox(self, sandbox_id: str) -> Optional[Sandbox]:
        """Get sandbox info."""
        return self.sandboxes.get(sandbox_id)

    def get_active_sandboxes(self) -> List[Sandbox]:
        """Get all running/starting sandboxes."""
        return [
            s for s in self.sandboxes.values()
            if s.status in (SandboxStatus.RUNNING, SandboxStatus.STARTING)
        ]

    def get_sandboxes_for_product(self, product_id: str) -> List[Sandbox]:
        """Get all sandboxes for a product."""
        return [
            s for s in self.sandboxes.values()
            if s.product_id == product_id
        ]

    def check_sandbox_health(self, sandbox_id: str) -> Dict[str, Any]:
        """
        Check if a sandbox is healthy.
        Returns health status with details.
        """
        sandbox = self._get_sandbox(sandbox_id)
        result = {
            "id": sandbox_id,
            "status": sandbox.status.value,
            "healthy": False,
            "running": False,
            "port_open": False,
            "uptime_seconds": None,
            "error": None,
        }
        
        if sandbox.status == SandboxStatus.RUNNING:
            result["running"] = True
            
            # Check if process is alive
            container_id = sandbox.metadata.get("container_id")
            if container_id:
                try:
                    inspect = subprocess.run(
                        ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    running = inspect.returncode == 0 and inspect.stdout.strip() == "true"
                    result["healthy"] = running
                    if not running:
                        result["error"] = "Container not running"
                        sandbox.status = SandboxStatus.FAILED
                        sandbox.error = "Container exited unexpectedly"
                        self._save_state()
                except Exception:
                    result["healthy"] = False
                    result["error"] = "Container health check failed"
            elif sandbox.pid:
                try:
                    os.kill(sandbox.pid, 0)  # Signal 0 = check existence
                    result["healthy"] = True
                except ProcessLookupError:
                    result["error"] = "Process not found"
                    sandbox.status = SandboxStatus.FAILED
                    sandbox.error = "Process died unexpectedly"
                    self._save_state()
            
            # Check uptime
            if sandbox.started_at:
                result["uptime_seconds"] = time.time() - sandbox.started_at
            
            # Check port
            if sandbox.port:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result["port_open"] = sock.connect_ex(("127.0.0.1", sandbox.port)) == 0
                sock.close()
        
        return result

    def monitor_all(self) -> List[Dict[str, Any]]:
        """
        Monitor all sandboxes and handle timeouts.
        Returns list of health statuses.
        """
        results = []
        now = time.time()
        
        for sandbox_id in list(self.sandboxes.keys()):
            sandbox = self.sandboxes[sandbox_id]
            
            # Check timeout
            if sandbox.status == SandboxStatus.RUNNING and sandbox.started_at:
                elapsed = now - sandbox.started_at
                if elapsed > sandbox.timeout_seconds:
                    logger.warning(f"Sandbox {sandbox_id} timed out after {elapsed:.0f}s")
                    sandbox.status = SandboxStatus.TIMEOUT
                    sandbox.error = f"Timed out after {sandbox.timeout_seconds}s"
                    self.stop_sandbox(sandbox_id, force=True)
                    self._save_state()
            
            results.append(self.check_sandbox_health(sandbox_id))
        
        return results

    # -----------------------------------------------------------------------
    # Resource Limits
    # -----------------------------------------------------------------------

    def set_resource_limits(self, sandbox_id: str, cpu_limit: float = 0.5, memory_limit_mb: int = 512) -> bool:
        """
        Set resource limits for a sandbox (best-effort on macOS/Linux).
        
        Args:
            sandbox_id: The sandbox to limit
            cpu_limit: CPU limit as fraction of core (0.0-1.0)
            memory_limit_mb: Memory limit in MB
        
        Returns:
            True if limits were applied
        """
        sandbox = self._get_sandbox(sandbox_id)
        if not sandbox.pid:
            return False
        
        try:
            import resource
            
            # Memory limit (RLIMIT_AS)
            memory_bytes = memory_limit_mb * 1024 * 1024
            try:
                resource.prlimit(sandbox.pid, resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            except (ImportError, AttributeError):
                pass  # prlimit not available on macOS
            
            # CPU time limit (RLIMIT_CPU)
            cpu_time_sec = int(sandbox.timeout_seconds * cpu_limit)
            try:
                resource.prlimit(sandbox.pid, resource.RLIMIT_CPU, (cpu_time_sec, cpu_time_sec))
            except (ImportError, AttributeError):
                pass
            
            logger.info(f"Resource limits set for sandbox {sandbox_id}: CPU={cpu_limit}, MEM={memory_limit_mb}MB")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to set resource limits for sandbox {sandbox_id}: {e}")
            return False

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    def _get_sandbox(self, sandbox_id: str) -> Sandbox:
        """Get sandbox or raise."""
        sandbox = self.sandboxes.get(sandbox_id)
        if not sandbox:
            raise KeyError(f"Sandbox not found: {sandbox_id}")
        return sandbox

    def _allocate_port(self) -> int:
        """Allocate a port from the range."""
        for port in self.port_range:
            if port not in self._allocated_ports:
                # Quick check if port is available
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()
                if result != 0:  # Port is free
                    self._allocated_ports.add(port)
                    return port
        
        raise RuntimeError("No available ports in range")

    def _release_port(self, port: int) -> None:
        """Release a port."""
        self._allocated_ports.discard(port)

    def _copy_code(self, src: Path, dst: Path) -> None:
        """Copy code files to sandbox directory."""
        for item in src.iterdir():
            s = src / item.name
            d = dst / item.name
            if s.is_dir():
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

    def _detect_start_command(self, work_dir: Path) -> Optional[List[str]]:
        """Auto-detect the start command for the code in work_dir."""
        # Check for common project types
        if (work_dir / "package.json").exists():
            return ["npm", "start"]
        elif (work_dir / "requirements.txt").exists() or list(work_dir.glob("*.py")):
            # Check for FastAPI/Flask
            main_files = list(work_dir.glob("main.py")) + list(work_dir.glob("app.py"))
            if main_files:
                return ["python", main_files[0].name]
            return ["python", "-m", "http.server", str(self._get_next_port())]
        elif (work_dir / "index.html").exists():
            return ["python", "-m", "http.server", str(self._get_next_port())]
        elif (work_dir / "Cargo.toml").exists():
            return ["cargo", "run"]
        elif (work_dir / "go.mod").exists():
            return ["go", "run", "."]
        
        return None

    def _get_next_port(self) -> int:
        """Get next available port without allocating."""
        for port in self.port_range:
            if port not in self._allocated_ports:
                return port
        return self.port_range.start

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    def _save_state(self) -> None:
        """Save sandbox state to disk."""
        try:
            state = {
                "sandboxes": {
                    sid: {
                        "id": s.id,
                        "product_id": s.product_id,
                        "status": s.status.value,
                        "port": s.port,
                        "work_dir": s.work_dir,
                        "pid": s.pid,
                        "created_at": s.created_at,
                        "started_at": s.started_at,
                        "stopped_at": s.stopped_at,
                        "timeout_seconds": s.timeout_seconds,
                        "metadata": s.metadata,
                        "error": s.error,
                    }
                    for sid, s in self.sandboxes.items()
                },
                "allocated_ports": list(self._allocated_ports),
            }
            self._state_file.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.error(f"Failed to save sandbox state: {e}")

    def _load_state(self) -> None:
        """Load sandbox state from disk."""
        try:
            if self._state_file.exists():
                state = json.loads(self._state_file.read_text())
                for sid, data in state.get("sandboxes", {}).items():
                    data["status"] = SandboxStatus(data["status"])
                    self.sandboxes[sid] = Sandbox(**data)
                self._allocated_ports = set(state.get("allocated_ports", []))
                logger.info(f"Loaded {len(self.sandboxes)} sandboxes from state")
        except Exception as e:
            logger.warning(f"Failed to load sandbox state: {e}")

    def cleanup_all(self) -> int:
        """Stop and destroy all sandboxes. Returns count."""
        count = len(self.sandboxes)
        for sandbox_id in list(self.sandboxes.keys()):
            try:
                self.destroy_sandbox(sandbox_id, cleanup_files=True)
            except Exception as e:
                logger.error(f"Failed to cleanup sandbox {sandbox_id}: {e}")
        logger.info(f"Cleaned up {count} sandboxes")
        return count
