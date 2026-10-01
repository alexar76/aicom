"""An import with no dependency entry only fails at build time, after install."""

import json
from pathlib import Path

from web.backend.services.duplicate_module_check import find_undeclared_frontend_deps


def _pkg(root: Path, deps: dict) -> None:
    (root / "frontend").mkdir(parents=True, exist_ok=True)
    (root / "frontend" / "package.json").write_text(
        json.dumps({"name": "f", "dependencies": deps}), encoding="utf-8"
    )


def _src(root: Path, rel: str, text: str) -> None:
    p = root / "frontend" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_the_real_case_is_caught(tmp_path):
    """TS2307: Cannot find module 'axios'."""
    _pkg(tmp_path, {"react": "^18"})
    _src(tmp_path, "src/api/client.ts", "import axios from 'axios';\n")
    found = find_undeclared_frontend_deps(tmp_path)
    assert [f["package"] for f in found] == ["axios"]


def test_declared_packages_pass(tmp_path):
    _pkg(tmp_path, {"react": "^18", "axios": "^1"})
    _src(tmp_path, "src/api/client.ts", "import axios from 'axios';\nimport React from 'react';\n")
    assert find_undeclared_frontend_deps(tmp_path) == []


def test_scoped_packages_use_their_full_name(tmp_path):
    _pkg(tmp_path, {"@tanstack/react-query": "^5"})
    _src(tmp_path, "src/a.ts", "import { useQuery } from '@tanstack/react-query';\n")
    assert find_undeclared_frontend_deps(tmp_path) == []


def test_subpath_imports_resolve_to_the_package(tmp_path):
    _pkg(tmp_path, {"lodash": "^4"})
    _src(tmp_path, "src/a.ts", "import merge from 'lodash/merge';\n")
    assert find_undeclared_frontend_deps(tmp_path) == []


def test_relative_and_alias_imports_are_not_packages(tmp_path):
    _pkg(tmp_path, {})
    _src(tmp_path, "src/a.ts", "import x from './b';\nimport y from '@/lib/c';\nimport z from 'node:fs';\n")
    assert find_undeclared_frontend_deps(tmp_path) == []


def test_dev_dependencies_count_as_declared(tmp_path):
    (tmp_path / "frontend").mkdir(parents=True)
    (tmp_path / "frontend" / "package.json").write_text(
        json.dumps({"name": "f", "devDependencies": {"vitest": "^1"}}), encoding="utf-8"
    )
    _src(tmp_path, "src/a.test.ts", "import { describe } from 'vitest';\n")
    assert find_undeclared_frontend_deps(tmp_path) == []


def test_each_package_is_reported_once(tmp_path):
    _pkg(tmp_path, {})
    _src(tmp_path, "src/a.ts", "import axios from 'axios';\n")
    _src(tmp_path, "src/b.ts", "import axios from 'axios';\n")
    assert len(find_undeclared_frontend_deps(tmp_path)) == 1
