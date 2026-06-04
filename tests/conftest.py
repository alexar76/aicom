# ============================================================================
# AUTONOMOUS AI-FACTORY v2.1 — Pytest Configuration & Fixtures
# ============================================================================

import os
import sys
import json
import pytest
import tempfile
import time
from pathlib import Path
from typing import Generator, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Stable JWT for tests that instantiate ``SecurityManager()`` without a secret (e.g. TestClient(app)).
os.environ.setdefault("JWT_SECRET_KEY", "0" * 48)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_environ():
    """Isolate process env per test.

    Several tests (and the code they exercise) mutate ``os.environ`` directly
    rather than via ``monkeypatch`` — e.g. ``apply_pipeline_db_config_from_app_config``
    writes ``PIPELINE_DB_BACKEND``/``USE_SQLITE``. Without this guard those writes
    leak into later tests and make outcomes order-dependent (a JSON-backend test
    silently switches to SQLite, etc.). Snapshot and restore around every test.
    """
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)

@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Create a temporary data directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        for subdir in ["config", "state", "logs", "secrets", "specs", "arch", "code", "bugs", "telemetry", "reports/director", "sandboxes"]:
            (data_dir / subdir).mkdir(parents=True, exist_ok=True)
        
        yield data_dir


@pytest.fixture
def sample_product_idea() -> str:
    """A sample product idea for testing."""
    return "Create a REST API for a task management system with user authentication, project CRUD, and real-time notifications."


@pytest.fixture
def sample_spec() -> Dict[str, Any]:
    """A sample product specification."""
    return {
        "product_name": "TaskManager API",
        "description": "A REST API for task management",
        "version": "1.0.0",
        "core_features": [
            "User authentication (JWT)",
            "Project CRUD operations",
            "Task management with status tracking",
            "Real-time notifications via WebSocket",
        ],
        "user_stories": [
            "As a user, I want to register and login securely",
            "As a user, I want to create and manage projects",
            "As a user, I want to assign tasks to team members",
        ],
        "estimated_effort": "medium",
        "target_audience": "Development teams",
        "tech_stack_hint": "Python/FastAPI",
    }


@pytest.fixture
def sample_architecture() -> Dict[str, Any]:
    """A sample architecture design."""
    return {
        "components": [
            {
                "name": "AuthService",
                "type": "service",
                "description": "Handles user authentication",
                "dependencies": [],
            },
            {
                "name": "ProjectService",
                "type": "service",
                "description": "Manages projects",
                "dependencies": ["AuthService"],
            },
            {
                "name": "TaskService",
                "type": "service",
                "description": "Manages tasks",
                "dependencies": ["AuthService", "ProjectService"],
            },
        ],
        "data_models": [
            {
                "name": "User",
                "fields": ["id", "username", "email", "password_hash", "created_at"],
            },
            {
                "name": "Project",
                "fields": ["id", "name", "description", "owner_id", "created_at"],
            },
            {
                "name": "Task",
                "fields": ["id", "title", "status", "assignee_id", "project_id", "created_at"],
            },
        ],
        "api_endpoints": [
            {"path": "/api/auth/register", "method": "POST"},
            {"path": "/api/auth/login", "method": "POST"},
            {"path": "/api/projects", "method": "GET,POST"},
            {"path": "/api/projects/{id}", "method": "GET,PUT,DELETE"},
            {"path": "/api/tasks", "method": "GET,POST"},
        ],
        "tech_stack": {
            "backend": "Python/FastAPI",
            "database": "PostgreSQL",
            "auth": "JWT + bcrypt",
            "realtime": "WebSocket",
        },
    }


@pytest.fixture
def sample_generated_code() -> Dict[str, Any]:
    """Sample generated code output."""
    return {
        "files": [
            {
                "path": "main.py",
                "content": "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\ndef root():\n    return {'message': 'Hello World'}\n",
            },
            {
                "path": "requirements.txt",
                "content": "fastapi==0.115.0\nuvicorn==0.30.6\n",
            },
        ],
        "dependencies": ["fastapi", "uvicorn"],
        "entry_point": "main.py",
    }


@pytest.fixture
def mock_llm_provider(mocker):
    """Mock LLM provider for testing agents."""
    provider = mocker.MagicMock()
    
    async def mock_generate(prompt, config=None):
        return '{"result": "mock_output"}'
    
    provider.generate = mock_generate
    return provider


@pytest.fixture
def sample_pipeline_state() -> Dict[str, Any]:
    """Sample pipeline state for testing."""
    return {
        "products": {
            "test-product-1": {
                "id": "test-product-1",
                "idea": "Test product idea",
                "state": "IDEA_RECEIVED",
                "created_at": 1000000.0,
                "tasks": [],
            }
        },
        "current_task_id": None,
    }


@pytest.fixture
def state_machine(tmp_path):
    """Create a PipelineStateMachine backed by a temp file."""
    from orchestrator.state_machine import PipelineStateMachine
    state_file = tmp_path / "state" / "pipeline.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    sm = PipelineStateMachine(str(state_file))
    sm.products = {}
    sm.task_queue = []
    return sm


@pytest.fixture
def product_with_task(state_machine, sample_product_idea):
    """Create a product with its first task queued."""
    from orchestrator.state_machine import Task, PipelineState
    import time
    product = state_machine.create_product(sample_product_idea)
    task = Task(
        id="task-initial",
        product_id=product.id,
        agent_type="analyst",
        state=PipelineState.MARKET_RESEARCHED,
        created_at=time.time(),
        priority=1,
    )
    state_machine.add_task_to_queue(task)
    return product, task


# ---------------------------------------------------------------------------
# New Fixtures — Task Specification Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_state_file(tmp_path) -> Path:
    """Returns a Path to a temporary pipeline.json state file."""
    path = tmp_path / "state" / "pipeline.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def sample_product():
    """Returns a properly structured Product dataclass instance."""
    from orchestrator.state_machine import Product, PipelineState
    return Product(
        id="test-prod-1",
        idea="A test product idea for unit testing",
        state=PipelineState.IDEA_RECEIVED,
        created_at=1000.0,
        updated_at=1000.0,
    )


@pytest.fixture
def sample_task():
    """Returns a properly structured Task dataclass instance."""
    from orchestrator.state_machine import Task, TaskStatus, PipelineState
    return Task(
        id="test-task-1",
        product_id="test-prod-1",
        agent_type="analyst",
        state=PipelineState.MARKET_RESEARCHED,
        status=TaskStatus.PENDING,
        created_at=1000.0,
        priority=5,
    )


@pytest.fixture
def pipeline_state_machine(tmp_state_file):
    """Returns a PipelineStateMachine backed by a temporary file."""
    from orchestrator.state_machine import PipelineStateMachine
    sm = PipelineStateMachine(str(tmp_state_file))
    sm.products = {}
    sm.task_queue = []
    return sm


def pytest_collection_modifyitems(config, items):
    """Skip FastAPI-heavy integration tests when optional deps are not installed."""
    try:
        import fastapi  # noqa: F401
        return
    except ImportError:
        skip = pytest.mark.skip(
            reason="install project requirements (fastapi/uvicorn) to run web integration tests",
        )
        for item in items:
            nid = getattr(item, "nodeid", "")
            if any(
                part in nid
                for part in (
                    "test_admin_auth.py",
                    "test_customer_journey_e2e.py",
                    "test_browser_fastapi_login_integration.py",
                )
            ):
                item.add_marker(skip)
