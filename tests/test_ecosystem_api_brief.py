"""A generated product should never have to guess the API of the factory that generated it.

The factory builds products that pay for capabilities from its own mesh, and the knowledge of how to
call them lived in two places, neither of which reached the agent writing the code: the ATLAS
catalogue (every capability id with its input schema) and a detector that compares a product's calls
against it. So a round was told

    Input for atlas.fire.weather@v1 does not match its published schema — field 'bbox' is not in it

and had to guess what the schema DOES accept. Three contract violations survived six rounds on the
live product, and the round that finally satisfied them did it by deleting the call.
"""

from __future__ import annotations

from pathlib import Path

from core.ecosystem_api_brief import (
    INVOKE_ENVELOPE,
    brief_for_code,
    capability_catalogue,
    render_brief,
)


def test_the_catalogue_is_read_from_the_satellite_that_owns_it():
    caps = capability_catalogue()
    assert len(caps) >= 5, "the ATLAS catalogue looks unreadable — annotated assignment?"
    ids = {str(c.get("capability_id")) for c in caps}
    assert "atlas.fire.weather@v1" in ids
    assert "atlas.situation.brief@v1" in ids


def test_the_brief_lists_the_fields_a_capability_accepts():
    brief = render_brief(capability_ids=["atlas.fire.weather@v1"])
    for field in ("west", "south", "east", "north"):
        assert field in brief, f"{field} missing — the round cannot construct a bbox without it"
    assert "atlas.fire.weather@v1" in brief


def test_the_envelope_names_the_two_legal_fields_and_the_traps():
    assert "capability_id" in INVOKE_ENVELOPE and '"input"' in INVOKE_ENVELOPE
    for wrong in ("'capability'", "'payload'", "'params'"):
        assert wrong in INVOKE_ENVELOPE, f"{wrong} was a real mistake on a real product"


def test_the_bbox_trap_is_called_out():
    """'bbox' was sent as one field to two capabilities that have no such field."""
    brief = render_brief()
    assert "west/south/east/north" in brief
    assert "never as a single 'bbox' field" in brief


def test_the_brief_narrows_to_what_a_product_mentions(tmp_path):
    code = tmp_path / "code"
    (code / "app").mkdir(parents=True)
    (code / "app" / "client.py").write_text(
        'CAP = "atlas.nearest.read@v1"\n', encoding="utf-8"
    )
    brief = brief_for_code(code)
    assert "atlas.nearest.read@v1" in brief
    assert "atlas.gnss.degradation.read@v1" not in brief, "a product gets its own capabilities"


def test_a_product_with_no_capabilities_gets_no_brief(tmp_path):
    code = tmp_path / "code"
    code.mkdir()
    (code / "main.py").write_text("print('hello')\n", encoding="utf-8")
    assert brief_for_code(code) == ""


def test_the_developer_agent_receives_it():
    dev = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "from core.ecosystem_api_brief import brief_for_code, render_brief" in dev
    block = dev[dev.index("_mesh_brief = \"\"") :][:1200]
    assert "admin_instructions = f\"{admin_instructions}" in block, "the brief must reach the prompt"
    assert '"@v1" in _blob' in block, "a product that only mentions capabilities in its spec counts"


def test_the_live_ecosystem_comes_before_the_bundled_snapshot():
    """The monorepo inside the image is a snapshot from build time and a container cannot refresh it.

    Which is the correction this module needed: it read the bundled ATLAS file first, so the factory's
    knowledge of its own ecosystem froze the moment an image was built. The hub's federated manifest is
    the ecosystem describing itself right now — 76 capabilities across three hubs when measured,
    against the 6 the bundled file knows. GitHub raw is second, because it is the only source a
    container can still pull when the hub is unreachable, and the bundled file is last: it is the only
    one that can go stale without anyone noticing.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "core" / "ecosystem_api_brief.py").read_text(
        encoding="utf-8"
    )
    body = src[src.index("def capability_catalogue(") :]
    body = body[: body.index("def render_brief(")]
    live_at = body.index("_live_capabilities()")
    github_at = body.index("_github_capabilities()")
    bundled_at = body.index('"atlas" / "atlas" / "products.py"')
    assert live_at < github_at < bundled_at, "the freshest source must be tried first"
    assert "_read_cache()" in body, "a round runs every few minutes; do not refetch every time"


def test_the_cache_expires():
    """A cache with no TTL is a snapshot with extra steps."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "core" / "ecosystem_api_brief.py").read_text(
        encoding="utf-8"
    )
    assert "CACHE_TTL_SEC" in src
    assert "+ CACHE_TTL_SEC < _time.time()" in src


def test_network_can_be_switched_off_for_offline_use():
    """Tests and air-gapped runs must still get the bundled catalogue."""
    caps = capability_catalogue(allow_network=False)
    assert len(caps) >= 5
    assert {str(c.get("capability_id")) for c in caps} >= {"atlas.fire.weather@v1"}


def test_github_is_named_as_the_second_source():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "core" / "ecosystem_api_brief.py").read_text(
        encoding="utf-8"
    )
    assert "raw.githubusercontent.com/alexar76/atlas" in src
