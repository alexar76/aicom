"""Runtime audits must not report clean when inventory or intelligence is missing."""
import io
import json
import subprocess
import urllib.error

import pytest

from scripts import deployed_versions as scan


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    report = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["deployed_versions.py", "--host", "owned.example", "--json", str(report)])
    monkeypatch.setattr(scan, "containers", lambda *args: ["app"])
    monkeypatch.setattr(scan, "node_deps", lambda *args: {"name": "app", "deps": {"example": "1.0.0"}})
    return report


def test_unreachable_osv_cannot_greenlight_runtime(runtime, monkeypatch, capsys):
    def unavailable(*args, **kwargs):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(scan.urllib.request, "urlopen", unavailable)
    assert scan.main() == 2
    assert "OK:" not in capsys.readouterr().out
    assert json.loads(runtime.read_text())["status"] == "incomplete"


@pytest.mark.parametrize("response", [{}, [], {"results": []}, {"results": [None]},
    {"results": [{"next_page_token": "more"}]}, {"results": [{"vulns": [{}]}]}])
def test_partial_osv_response_fails_closed(runtime, monkeypatch, response):
    monkeypatch.setattr(scan.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(response).encode()))
    assert scan.main() == 2


@pytest.mark.parametrize("metadata", [None, [], {}, {"severity": "UNKNOWN"}])
def test_missing_advisory_severity_is_not_clean(runtime, monkeypatch, metadata):
    monkeypatch.setattr(scan, "osv_lookup", lambda pairs: {pairs[0]: ["GHSA-example"]})
    response = json.dumps({"id": "GHSA-example", "database_specific": metadata}).encode()
    monkeypatch.setattr(scan.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(response))
    assert scan.main() == 2


def test_empty_inventory_is_incomplete(runtime, monkeypatch):
    monkeypatch.setattr(scan, "containers", lambda *a: [])
    assert scan.main() == 2


def test_verified_clean_batch_passes(runtime, monkeypatch):
    monkeypatch.setattr(scan.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b'{"results":[{}]}'))
    assert scan.main() == 0
    assert json.loads(runtime.read_text())["status"] == "complete"


@pytest.mark.parametrize("result", [subprocess.CompletedProcess([], 255, "", "connection failed"),
                                   subprocess.TimeoutExpired("ssh", 180)])
def test_ssh_failure_is_never_an_empty_success(monkeypatch, result):
    def run(*args, **kwargs):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(scan.subprocess, "run", run)
    with pytest.raises(scan.IncompleteScan):
        scan.containers("owned.example", None)


@pytest.mark.parametrize("payload", ["", "not json", "null", "{}", '{"deps":{"example":null}}'])
def test_invalid_node_probe_is_incomplete(monkeypatch, payload):
    monkeypatch.setattr(scan, "ssh", lambda *args: payload)
    with pytest.raises(scan.IncompleteScan):
        scan.node_deps("owned.example", None, "app")


def test_explicit_non_node_container_is_skipped(monkeypatch):
    monkeypatch.setattr(scan, "ssh", lambda *args: '{"skipped":"no-node"}')
    assert scan.node_deps("owned.example", None, "nginx") == {}
