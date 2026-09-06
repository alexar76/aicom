"""A class body executes top to bottom, and nothing in the pipeline knew that.

The product's last defect, in full:

    class AtlasClient:
        invoke = invoke_capability          # line 8: NameError at import
        async def invoke(self, capability, payload):
            return await self.invoke_capability(capability, payload)

The round wrote both halves of a fix and left the failed first half in place. The wrapper below is
correct; the line above stops the app from importing at all.

Nothing saw it. `undefined_names_in_source` returned `[]`, `find_undefined_names` returned `[]`, the
tree scored **0** — because a scope-wide name collector finds `invoke_capability` in the class
namespace and never asks whether it was bound *before* the line that reads it.

That blindness deadlocked the product. With the score at zero, any fix to the file measured as no
improvement while any incidental change measured as risk, so the round guard gave the fix back every
time — three rounds running, on the one defect standing between the product and booting.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.duplicate_module_check import find_class_body_forward_refs


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_the_live_defect_is_found(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/services/atlas_client.py": (
                "class AtlasClient:\n"
                "    invoke = invoke_capability\n"
                "    async def invoke_capability(self, c, p):\n"
                "        return {}\n"
            )
        },
    )
    found = find_class_body_forward_refs(code)
    assert len(found) == 1, found
    assert found[0]["name"] == "invoke_capability"
    assert found[0]["line"] == 2
    assert found[0]["class"] == "AtlasClient"
    assert found[0]["severity"] == "critical"
    assert "delete it" in found[0]["detail"], "the finding does not say what to do"


def test_a_name_bound_earlier_in_the_body_is_fine(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/a.py": (
                "class C:\n"
                "    def real(self):\n"
                "        return 1\n"
                "    alias = real\n"
            )
        },
    )
    assert find_class_body_forward_refs(code) == []


def test_a_module_level_name_is_fine(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/a.py": (
                "from enum import Enum\n"
                "DEFAULT = 3\n\n"
                "class C(Enum):\n"
                "    size = DEFAULT\n"
            )
        },
    )
    assert find_class_body_forward_refs(code) == []


def test_a_method_body_reading_a_later_method_is_fine(tmp_path):
    """That resolves when the method is called, which is a different question."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/a.py": (
                "class C:\n"
                "    def first(self):\n"
                "        return self.second()\n"
                "    def second(self):\n"
                "        return 1\n"
            )
        },
    )
    assert find_class_body_forward_refs(code) == []


def test_a_lambda_parameter_is_not_a_forward_reference(tmp_path):
    """The first version reported five criticals about a name called `x`.

    `Column(default=lambda x: ...)` in a SQLAlchemy model body — the lambda binds its own parameter,
    and a detector that reports `critical` cannot afford to miss that.
    """
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/models/analytics.py": (
                "from sqlalchemy import Column, String\n\n"
                "class Dashboard:\n"
                "    name = Column(String, default=lambda x: str(x))\n"
                "    tags = Column(String, default=lambda: ','.join(t for t in ['a']))\n"
            )
        },
    )
    assert find_class_body_forward_refs(code) == []


def test_a_comprehension_target_is_not_a_forward_reference(tmp_path):
    code = _tree(
        tmp_path / "code",
        {"backend/app/a.py": "class C:\n    items = [i * 2 for i in range(3)]\n"},
    )
    assert find_class_body_forward_refs(code) == []


def test_a_method_name_does_not_count_as_module_scope(tmp_path):
    """Walking the whole tree for module scope is what made the detector silent on the live case.

    `invoke_capability` is a method of the class, so a module-scope collector built with `ast.walk`
    found it and concluded the line was fine — on the exact defect this exists to catch.
    """
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/a.py": (
                "class C:\n"
                "    alias = later\n"
                "    def later(self):\n"
                "        return 1\n"
            )
        },
    )
    assert [f["name"] for f in find_class_body_forward_refs(code)] == ["later"]


def test_a_decorator_is_evaluated_with_the_body(tmp_path):
    """Unlike a method body, a decorator runs at class-definition time."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/a.py": (
                "class C:\n"
                "    @missing_decorator\n"
                "    def go(self):\n"
                "        return 1\n"
            )
        },
    )
    assert [f["name"] for f in find_class_body_forward_refs(code)] == ["missing_decorator"]


def test_an_unparseable_file_is_skipped(tmp_path):
    code = _tree(tmp_path / "code", {"backend/app/a.py": "class C:\n    def (:\n"})
    assert find_class_body_forward_refs(code) == []


def test_builtins_are_fine(tmp_path):
    code = _tree(
        tmp_path / "code",
        {"backend/app/a.py": "class C:\n    kind = str\n    size = len('abc')\n"},
    )
    assert find_class_body_forward_refs(code) == []


def test_it_is_wired_everywhere_it_has_to_be():
    """A detector the ratchet cannot see is a detector that deadlocks the ratchet."""
    root = Path(__file__).resolve().parents[1]

    check = (root / "web" / "backend" / "services" / "duplicate_module_check.py").read_text(encoding="utf-8")
    assert "forward_refs = find_class_body_forward_refs(code_dir)" in check
    assert '"code": "class_body_forward_ref"' in check
    # The property, not the exact spelling: this assertion broke the moment a term was added after it,
    # which is a test asserting punctuation rather than behaviour.
    passed_expr = check[check.index('"passed": not missing') : check.index('"skipped": False')]
    assert "not forward_refs" in passed_expr, "a critical that does not fail its own gate"

    dev = (root / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "10 * len(find_class_body_forward_refs(code_root, limit=200))" in score, (
        "the round guard still cannot see it, so it will keep giving the fix back"
    )

    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    head = qa[: qa.index("# Deletions next")]
    assert '"class_body_forward_ref"' in head


def test_the_rejection_log_can_name_this_class():
    """The score counted it while the breakdown did not, so a rejection would have read
    "nothing individually — check the weights" — the exact uninformative message the breakdown was
    built to replace."""
    dev = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    breakdown = dev[dev.index("def _tree_defect_breakdown(") : dev.index("def _breakdown_delta(")]
    assert '"class_body_forward_ref"' in breakdown
    ids = dev[dev.index("def _tree_defect_identities(") : dev.index("def _identities_appeared(")]
    assert '"class_body_forward_ref"' in ids
