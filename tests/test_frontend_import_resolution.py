"""A relative import pointing at nothing breaks the build hardest and is cheap to see."""

from pathlib import Path

from web.backend.services.duplicate_module_check import find_unresolved_frontend_imports


def _w(root: Path, rel: str, text: str = "export const x = 1\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_missing_relative_module_is_reported(tmp_path):
    root = tmp_path / "code"
    _w(root, "frontend/src/pages/Home.tsx", "import { getAdvisory } from '../api/client';\n")
    found = find_unresolved_frontend_imports(root)
    assert [f["import"] for f in found] == ["../api/client"]


def test_extensionless_sibling_resolves(tmp_path):
    root = tmp_path / "code"
    _w(root, "frontend/src/api/client.ts")
    _w(root, "frontend/src/pages/Home.tsx", "import { x } from '../api/client';\n")
    assert find_unresolved_frontend_imports(root) == []


def test_directory_index_resolves(tmp_path):
    root = tmp_path / "code"
    _w(root, "frontend/src/hooks/index.ts")
    _w(root, "frontend/src/App.tsx", "import { x } from './hooks';\n")
    assert find_unresolved_frontend_imports(root) == []


def test_tsx_and_css_targets_resolve(tmp_path):
    root = tmp_path / "code"
    _w(root, "frontend/src/pages/Login.tsx")
    _w(root, "frontend/src/pages/Login.css", "body{}\n")
    _w(root, "frontend/src/App.tsx", "import Login from './pages/Login';\nimport './pages/Login.css';\n")
    assert find_unresolved_frontend_imports(root) == []


def test_package_imports_are_ignored(tmp_path):
    """Only relative specifiers are checked; node_modules is not our business."""
    root = tmp_path / "code"
    _w(root, "frontend/src/App.tsx", "import React from 'react';\nimport axios from 'axios';\n")
    assert find_unresolved_frontend_imports(root) == []


def test_export_from_is_checked_too(tmp_path):
    root = tmp_path / "code"
    _w(root, "frontend/src/index.ts", "export { thing } from './gone';\n")
    assert len(find_unresolved_frontend_imports(root)) == 1


def test_findings_are_capped(tmp_path):
    root = tmp_path / "code"
    body = "\n".join(f"import a{i} from './missing{i}';" for i in range(30))
    _w(root, "frontend/src/App.tsx", body)
    assert len(find_unresolved_frontend_imports(root, limit=4)) == 4
