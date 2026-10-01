"""Tests for optional neural reference template selection (no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web.backend.services import reference_templates as rt


def test_templates_dir_respects_env_override(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_REFERENCE_TEMPLATES_DIR", raising=False)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    assert rt.templates_dir_from_env() == tmp_path / "reference_templates"

    custom = tmp_path / "my_refs"
    monkeypatch.setenv("AIFACTORY_REFERENCE_TEMPLATES_DIR", str(custom))
    assert rt.templates_dir_from_env() == custom


def test_pick_random_stable_per_product(tmp_path, monkeypatch):
    root = tmp_path / "reference_templates"
    root.mkdir(parents=True)
    manifest = {
        "templates": [
            {"id": "a", "title": "A", "path": "t1"},
            {"id": "b", "title": "B", "path": "t2"},
        ]
    }
    (root / "t1").mkdir()
    (root / "t1" / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / "t2").mkdir()
    (root / "t2" / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setenv("AIFACTORY_REFERENCE_TEMPLATE_MODE", "random")
    a = rt.pick_template_folder_name(
        root,
        product_id="prod-aaa",
        specification={},
        admin_instructions="",
        manifest=manifest,
    )
    b = rt.pick_template_folder_name(
        root,
        product_id="prod-aaa",
        specification={},
        admin_instructions="",
        manifest=manifest,
    )
    assert a == b
    assert a in ("t1", "t2")


def test_round_robin_advances(tmp_path, monkeypatch):
    root = tmp_path / "reference_templates"
    root.mkdir(parents=True)
    manifest = {
        "templates": [
            {"path": "t1"},
            {"path": "t2"},
        ]
    }
    for t in ("t1", "t2"):
        (root / t).mkdir()
        (root / t / "index.html").write_text("x", encoding="utf-8")

    monkeypatch.setenv("AIFACTORY_REFERENCE_TEMPLATE_MODE", "round_robin")
    first = rt.pick_template_folder_name(
        root,
        product_id="any",
        specification={},
        admin_instructions="",
        manifest=manifest,
    )
    second = rt.pick_template_folder_name(
        root,
        product_id="any",
        specification={},
        admin_instructions="",
        manifest=manifest,
    )
    assert first != second
    st_path = root / "._selection_state.json"
    assert st_path.is_file()
    st = json.loads(st_path.read_text(encoding="utf-8"))
    assert int(st.get("round_robin_index", 0)) >= 2


def test_build_prompt_empty_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_REFERENCE_TEMPLATES_ENABLED", "0")
    (tmp_path / "reference_templates").mkdir(parents=True)
    block = rt.build_reference_template_prompt_block(
        product_id="p1",
        specification={},
        admin_instructions="",
        data_root=tmp_path,
    )
    assert block == ""


def test_list_reference_templates_catalog_manifest_and_orphan(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_REFERENCE_TEMPLATES_DIR", raising=False)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    root = tmp_path / "reference_templates"
    root.mkdir(parents=True)
    (root / "listed").mkdir(parents=True)
    (root / "listed" / "index.html").write_text("<html/>", encoding="utf-8")
    (root / "orphan").mkdir(parents=True)
    (root / "orphan" / "index.html").write_text("<html/>", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "templates": [
                    {"id": "listed", "title": "Listed", "path": "listed", "files": ["index.html"]},
                ]
            }
        ),
        encoding="utf-8",
    )

    cat = rt.list_reference_templates_catalog(tmp_path)
    paths = {c["path"] for c in cat}
    assert paths == {"listed", "orphan"}
    titles = {c["path"]: c["title"] for c in cat}
    assert titles["listed"] == "Listed"


def test_upsert_reference_template_upload_writes_meta_and_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_REFERENCE_TEMPLATES_DIR", raising=False)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    manifest = rt.upsert_reference_template_upload(
        tmp_path,
        "my-shell",
        "My Shell",
        [
            ("index.html", "<!DOCTYPE html><html><body>x</body></html>"),
            ("style.css", "body{margin:0}"),
        ],
    )
    assert len(manifest.get("templates") or []) >= 1
    dest = tmp_path / "reference_templates" / "my-shell"
    assert (dest / "index.html").is_file()
    assert (dest / "reference.meta.json").is_file()
    meta = json.loads((dest / "reference.meta.json").read_text(encoding="utf-8"))
    assert meta.get("title") == "My Shell"


def test_build_prompt_includes_html_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_REFERENCE_TEMPLATES_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_REFERENCE_TEMPLATE_MODE", "fixed")
    monkeypatch.setenv("AIFACTORY_REFERENCE_TEMPLATE_ID", "neon")

    root = tmp_path / "reference_templates"
    (root / "neon").mkdir(parents=True)
    (root / "neon" / "index.html").write_text("<html><body>NEON_REF</body></html>", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"templates": [{"path": "neon"}]}),
        encoding="utf-8",
    )

    block = rt.build_reference_template_prompt_block(
        product_id="p1",
        specification={},
        admin_instructions="",
        data_root=tmp_path,
    )
    assert "NEON_REF" in block
    assert "NEURAL UI REFERENCE" in block
