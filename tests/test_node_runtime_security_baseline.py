"""Build inputs must not silently select an unpatched Node runtime.

The 2026-10-21 security release fixes the 22.x line in 22.23.4. These checks
inspect tracked Docker/Compose inputs without building images or contacting a
registry. Official image-tag and checksum evidence is in the security audit.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FLOOR = (22, 23, 4)
ARCHIVE_SHA256 = {
    "arm64": "6287aa46b6c375d816e63ae66d024fbbfd70404825aabdfdf898a970871d2f4b",
    "x64": "1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce",
}


def _tracked_build_files() -> list[Path]:
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True).split("\0")
    return [ROOT / name for name in paths if name and (
        "Dockerfile" in Path(name).name or Path(name).suffix in {".yml", ".yaml"}
    )]


def _secure_node_tag(image: str) -> bool:
    match = re.fullmatch(r"node:(\d+)\.(\d+)\.(\d+)(?:[-@].*)?", image)
    if not match:
        return False
    version = tuple(map(int, match.groups()))
    return version[0] == FLOOR[0] and version >= FLOOR


@pytest.mark.parametrize("image", ["node:20-alpine", "node:22", "node:22-alpine", "node:22.22.1-slim", "node:22.23.3"])
def test_unpatched_and_floating_node_tags_are_rejected(image):
    assert not _secure_node_tag(image)


@pytest.mark.parametrize("image", ["node:22.23.4-alpine", "node:22.23.4-bookworm-slim", "node:22.24.0-slim"])
def test_security_patch_and_later_same_line_tags_are_accepted(image):
    assert _secure_node_tag(image)


def test_tracked_docker_and_compose_node_images_meet_security_floor():
    checked = []
    for path in _tracked_build_files():
        source = path.read_text()
        arguments = dict(re.findall(r"(?m)^\s*ARG\s+(\w+)=(\S+)", source))
        for line in source.splitlines():
            match = re.match(r"\s*FROM\s+(?:--platform=\S+\s+)?(node:\S+)", line, re.I)
            if not match:
                match = re.match(r"\s*image:\s*[\"']?(node:[^\s\"']+)", line)
            if not match:
                continue
            image = re.sub(r"\$\{(\w+)\}", lambda m: arguments.get(m[1], m[0]), match[1])
            assert _secure_node_tag(image), f"{path.relative_to(ROOT)} selects {image}"
            checked.append(path)
    assert len(checked) >= 40, "tracked build scan missed expected Node image inputs"


@pytest.mark.parametrize("relative", [
    "independent/kova-gateway/Dockerfile",
    "independent/verified-execution-hub/Dockerfile",
    "independent/verified-execution-hub/docker/relay.Dockerfile",
])
def test_downloaded_node_archives_have_matching_version_and_checksums(relative):
    source = (ROOT / relative).read_text()
    assert "ARG NODE_VERSION=22.23.4" in source
    for arch, expected in ARCHIVE_SHA256.items():
        match = re.search(rf'node_arch="{arch}"; node_sha="([a-f0-9]+)"', source)
        assert match and match[1] == expected, f"{relative}: stale {arch} archive checksum"
    assert '| sha256sum -c -' in source


def test_root_apt_install_guard_rejects_old_runtime_versions():
    source = (ROOT / "Dockerfile").read_text()
    assert "node_22.x" in source and "node_20.x" not in source
    match = re.search(r"&& node -e '([^']+)'", source)
    assert match, "root image must fail closed when apt serves an older Node patch"
    node = shutil.which("node")
    assert node, "Node is needed to validate the actual Docker build version guard"
    for version, allowed in [("20.20.2", False), ("22.22.1", False), ("22.23.3", False),
                             ("22.23.4", True), ("22.24.0", True)]:
        fixture = f'Object.defineProperty(process.versions, "node", {{value: "{version}"}});'
        result = subprocess.run([node, "-e", fixture + match[1]], capture_output=True, text=True)
        assert (result.returncode == 0) is allowed, f"version guard mishandled {version}"


@pytest.mark.parametrize("relative", ["docker-compose.everything.yml", "lottery/docker-compose.yml"])
def test_updated_compose_files_parse_and_select_the_patched_node_image(relative):
    # Compose's !override is a data tag; accept it without enabling any Python
    # object constructors while parsing the merged-stack source.
    class ComposeLoader(yaml.SafeLoader):
        pass

    ComposeLoader.add_constructor("!override", lambda loader, node: loader.construct_sequence(node))
    document = yaml.load((ROOT / relative).read_text(), Loader=ComposeLoader)
    images = [service.get("image", "") for service in document["services"].values()]
    assert "node:22.23.4-alpine" in images
