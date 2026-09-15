"""create_all() only creates tables for models that were imported."""

from pathlib import Path

from web.backend.services.duplicate_module_check import find_unregistered_models


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


MODELS = {
    "backend/app/models/__init__.py": "from .operator import Operator\nfrom .budget_spend import BudgetSpend\n",
    "backend/app/models/operator.py": "class Operator(Base):\n    __tablename__ = 'operators'\n",
    "backend/app/models/budget_spend.py": "class BudgetSpend(Base):\n    __tablename__ = 'budget_spends'\n",
}


def _product(tmp_path: Path, main_src: str) -> Path:
    root = tmp_path / "code" / "prod-x"
    for rel, text in MODELS.items():
        _w(root, rel, text)
    _w(root, "backend/app/main.py", main_src)
    return root


def test_the_real_case_is_caught(tmp_path):
    """Login worked; /api/operator/spend 500'd on 'no such table: budget_spends'."""
    root = _product(tmp_path, "from app.db import engine\nBase.metadata.create_all(bind=engine)\n")
    found = find_unregistered_models(root)
    assert len(found) == 1
    assert found[0]["file"] == "backend/app/main.py"
    assert "budget_spend" in found[0]["models"]


def test_importing_the_models_package_satisfies_it(tmp_path):
    root = _product(
        tmp_path, "from app import models\nBase.metadata.create_all(bind=engine)\n"
    )
    assert find_unregistered_models(root) == []


def test_relative_package_import_satisfies_it(tmp_path):
    root = _product(tmp_path, "from ..models import Base\nBase.metadata.create_all(bind=engine)\n")
    assert find_unregistered_models(root) == []


def test_importing_a_specific_model_module_satisfies_it(tmp_path):
    root = _product(
        tmp_path,
        "from app.models.budget_spend import BudgetSpend\nBase.metadata.create_all(bind=engine)\n",
    )
    assert find_unregistered_models(root) == []


def test_no_create_all_means_nothing_to_report(tmp_path):
    root = _product(tmp_path, "app = FastAPI()\n")
    assert find_unregistered_models(root) == []


def test_a_product_with_no_models_is_ignored(tmp_path):
    root = tmp_path / "code" / "prod-none"
    _w(root, "backend/app/main.py", "Base.metadata.create_all(bind=engine)\n")
    assert find_unregistered_models(root) == []
