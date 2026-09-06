"""Each product must deploy to its own Vercel project, not a shared one."""

import re
from pathlib import Path

SOURCE = Path("web/backend/services/auto_publish.py").read_text(encoding="utf-8")


def test_bundle_directory_is_named_for_the_product():
    """Vercel derives the project name from the deployed directory name.

    A constant directory name puts every product in one project and each deploy
    overwrites the previous product's site.
    """
    m = re.search(r"bundle_dir = ([^\n]+)", SOURCE)
    assert m, "bundle_dir assignment not found"
    expr = m.group(1)
    assert expr.rstrip().endswith("product_id"), (
        f"bundle directory must end with the product id, got: {expr}"
    )


def test_the_old_shared_name_is_gone_from_the_path_expression():
    """The comment may still name it; the path must not end in it."""
    m = re.search(r"bundle_dir = ([^\n]+)", SOURCE)
    assert "vercel_bundle" not in m.group(1), "shared bundle directory name still used"


def test_the_reason_is_recorded_next_to_the_code():
    assert "overwriting the last" in SOURCE
