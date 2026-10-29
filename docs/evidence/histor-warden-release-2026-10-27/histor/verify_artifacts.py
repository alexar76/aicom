"""Read-only check of archived HISTOR artifacts, source hashes and optional rebuild."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def main() -> None:
    evidence = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=evidence.parents[3])
    parser.add_argument("--artifact-dir", type=Path, default=evidence / "artifacts")
    parser.add_argument("--rebuilt-wheel", type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    package = root / "histor"
    manifest = json.loads((evidence / "artifact-manifest.json").read_text())
    files = {
        kind: args.artifact_dir / Path(manifest["artifactHashes"][kind]["path"]).name
        for kind in ("wheel", "sdist")
    }
    for kind, path in files.items():
        assert sha(path.read_bytes()) == manifest["artifactHashes"][kind]["sha256"], kind
    with zipfile.ZipFile(files["wheel"]) as archive:
        wheel = {name: archive.read(name) for name in archive.namelist()}
    if args.rebuilt_wheel is not None:
        assert files["wheel"].read_bytes() == args.rebuilt_wheel.read_bytes(), "rebuilt wheel bytes differ"
    metadata_name = "aimarket_histor-0.5.0.dist-info/METADATA"
    meta = BytesParser().parsebytes(wheel[metadata_name])
    assert meta["Name"] == "aimarket-histor" and meta["Version"] == "0.5.0"
    assert meta["Metadata-Version"] == "2.4"
    assert meta["Requires-Python"] == ">=3.11"
    source_hashes = {}
    for name, body in wheel.items():
        if name.startswith("histor/"):
            assert body == (package / name).read_bytes(), name
            source_hashes["histor/" + name] = sha(body)
        else:
            assert name.startswith("aimarket_histor-0.5.0.dist-info/"), name
    with tarfile.open(files["sdist"]) as archive:
        sdist = {}
        for item in archive:
            assert item.isfile(), item.name
            name = item.name.removeprefix("aimarket_histor-0.5.0/")
            assert name != item.name, item.name
            assert not set(Path(name).parts).intersection({".venv", "node_modules", "__pycache__", "data"}), name
            assert not name.startswith("docs/evidence/"), name
            body = archive.extractfile(item).read()
            sdist[name] = body
            if name == "PKG-INFO":
                assert body == wheel[metadata_name]
            else:
                assert body == (package / name).read_bytes(), name
                source_hashes["histor/" + name] = sha(body)
    required = {"docs/upgrade-brief.md", "docs/upgrade-brief.ru.md", "docs/upgrade-brief.es.md",
                "docs/upgrade-brief.fr.md", "docs/upgrade-brief.zh.md"}
    assert required <= sdist.keys()
    examples = {str(path.relative_to(package)) for path in (package / "examples").rglob("*") if path.is_file()}
    assert examples <= sdist.keys(), sorted(examples - sdist.keys())
    for name in ("pyproject.toml", "uv.lock", "CHANGELOG.md", "histor/__init__.py"):
        source_hashes["histor/" + name] = sha((package / name).read_bytes())
    recorded_hashes = json.loads((evidence / "source-files.sha256.json").read_text())
    assert source_hashes == recorded_hashes, "packaged/current sources differ from frozen source manifest"
    result = {
        "distribution": "aimarket-histor",
        "version": "0.5.0",
        "metadataVersion": "2.4",
        "artifactHashes": {key: {"path": str(path), "sha256": sha(path.read_bytes()),
                                 "bytes": path.stat().st_size} for key, path in files.items()},
        "wheelMembers": len(wheel), "sdistMembers": len(sdist),
        "exampleFiles": len(examples), "localizedGuides": len(required),
        "sdistRebuiltWheelByteIdentical": True if args.rebuilt_wheel is not None else None,
        "frozenArtifactManifestUnchanged": True,
        "frozenSourceManifestMatched": True,
        "verifiedSourceHashes": len(source_hashes),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
