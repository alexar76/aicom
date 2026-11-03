"""Every list endpoint's page size is named, and page_limit clamps the way the inline code did."""

import pytest

from aimarket_hub.paging import page_limit


@pytest.mark.parametrize(
    ("value", "default", "maximum", "rows"),
    [
        (None, 200, 500, 200),   # no limit named: the default page
        (0, 200, 500, 200),      # zero reads as "no limit named" when there is a default
        (0, None, 500, 1),       # without a default, zero still returns one row
        (-5, None, 500, 1),
        (10_000, 200, 500, 500),  # never more than the maximum
        ("30", 200, 500, 30),     # query strings arrive as text
        (7, 1, 5_000, 7),
    ],
)
def test_page_limit_matches_the_inline_clamp(value, default, maximum, rows):
    assert page_limit(value, default=default, maximum=maximum) == rows
    inline = max(1, min(int(value or default), maximum)) if default is not None else max(1, min(int(value), maximum))
    assert page_limit(value, default=default, maximum=maximum) == inline


def test_a_value_that_is_not_a_number_is_refused_as_before():
    with pytest.raises(ValueError):
        page_limit("ten", maximum=50)


def test_no_list_endpoint_clamps_with_bare_numbers():
    """The review question was "200, 500 — where from?": every page size now has a name."""
    import re
    from pathlib import Path

    pkg = Path(__file__).resolve().parents[1] / "aimarket_hub"
    bare = re.compile(r"max\(1, min\(int\([^)]*\), \d|min\(max\(1, int\(limit\)\), \d")
    offenders = [
        f"{p.relative_to(pkg)}:{n}"
        for p in pkg.rglob("*.py")
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if bare.search(line) and p.name != "paging.py"
    ]
    assert not offenders, offenders
