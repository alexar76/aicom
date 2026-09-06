"""The missing-import class: a name used but never bound, surviving many rounds."""

from pathlib import Path

from web.backend.services.duplicate_module_check import find_undefined_names


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_the_production_bug_is_caught(tmp_path):
    """scoring.py imported everything except Boolean, then used Boolean."""
    root = tmp_path / "code"
    _write(
        root,
        "backend/app/models/scoring.py",
        "from sqlalchemy import Column, String, Integer\n"
        "\n"
        "class MetricDefinition:\n"
        "    name = Column(String, nullable=False)\n"
        "    is_active = Column(Boolean, default=True)\n",
    )
    found = find_undefined_names(root)
    assert [f["name"] for f in found] == ["Boolean"]
    assert found[0]["line"] == 5


def test_imports_aliases_and_dotted_modules_count_as_bound(tmp_path):
    root = tmp_path / "code"
    _write(
        root,
        "backend/app/a.py",
        "import os.path\nimport numpy as np\nfrom typing import Any as A\n"
        "x = os.path.join('a')\ny = np.array([])\nz: A = 1\n",
    )
    assert find_undefined_names(root) == []


def test_builtins_and_dunders_are_not_reported(tmp_path):
    root = tmp_path / "code"
    _write(
        root,
        "backend/app/b.py",
        "print(len([1]), isinstance(1, int), __name__)\n"
        "try:\n    pass\nexcept ValueError as e:\n    print(e)\n",
    )
    assert find_undefined_names(root) == []


def test_names_bound_anywhere_in_the_module_are_accepted(tmp_path):
    """Flattened scoping: bound in one function, used in another → not reported."""
    root = tmp_path / "code"
    _write(
        root,
        "backend/app/c.py",
        "def make():\n    helper = 1\n    return helper\n\n"
        "def use():\n    return helper\n",
    )
    assert find_undefined_names(root) == []


def test_comprehensions_args_walrus_and_for_targets_bind(tmp_path):
    root = tmp_path / "code"
    _write(
        root,
        "backend/app/d.py",
        "def f(a, *args, b=2, **kw):\n"
        "    return [i + a + b for i in args] + [j for j in kw]\n"
        "for row in []:\n    print(row)\n"
        "with open('x') as fh:\n    print(fh)\n"
        "if (n := 3) > 1:\n    print(n)\n",
    )
    assert find_undefined_names(root) == []


def test_class_attributes_and_decorators_bind(tmp_path):
    root = tmp_path / "code"
    _write(
        root,
        "backend/app/e.py",
        "from functools import lru_cache\n"
        "class C:\n"
        "    x = 1\n"
        "    @lru_cache\n"
        "    def m(self):\n"
        "        return self.x\n"
        "c = C()\n",
    )
    assert find_undefined_names(root) == []


def test_star_import_modules_are_skipped(tmp_path):
    """A star import can supply anything; accusing that file would be a false alarm."""
    root = tmp_path / "code"
    _write(root, "backend/app/f.py", "from sqlalchemy import *\nx = Column(Boolean)\n")
    assert find_undefined_names(root) == []


def test_syntax_errors_are_left_to_the_compiler(tmp_path):
    root = tmp_path / "code"
    _write(root, "backend/app/g.py", "def broken(:\n    pass\n")
    assert find_undefined_names(root) == []


def test_findings_are_capped(tmp_path):
    root = tmp_path / "code"
    body = "\n".join(f"v{i} = Missing{i}" for i in range(40))
    _write(root, "backend/app/h.py", body)
    assert len(find_undefined_names(root, limit=5)) == 5
